from openai import OpenAI

from core.answer_contract_runtime import AnswerContractRuntime
from core.cloud_export import (
    CloudExportDenied, CloudExportGrant, admit_cloud_initial,
    admit_cloud_tool_followup, admit_cloud_sdk_request,
)

from tools.tool_admission import admitted_tools, provider_tool_scope, current_turn_authority

from tools.tool_registry import (
    CLOUD_TOOLS,
    execute_tool,
)


MODEL = "gpt-5.6-luna"


def create_client(
    api_key
):
    return OpenAI(
        api_key=api_key
    )


def get_response(
    client,
    user_input,
    instructions,
    previous_response_id=None,
    allow_cloud_escalation=False,
    core_answer_contract=None,
    cloud_export=None,
):
    # This provider does not run the local grounded-public, spoiler or
    # conversational acceptance validators. Enforce narrow contract capability
    # at the router as well; provider ingress cannot silently claim parity.
    if core_answer_contract is not None:
        if not isinstance(core_answer_contract, AnswerContractRuntime) or core_answer_contract.source != "structured":
            raise ValueError("Cloud provider requires structured Core authority.")
        if (
            core_answer_contract.required_claims
            or core_answer_contract.verified_evidence_claims
            or core_answer_contract.metadata
            or core_answer_contract.epistemic_mode not in {
                "conversation", "classify_then_verify", "subjective",
            }
        ):
            raise ValueError("Cloud provider cannot satisfy these mandatory Core obligations.")

    # S3 is independent from S2 execution admission.  No grant means no SDK
    # request, even if the caller supplied plausible-looking instructions.
    if not isinstance(cloud_export, CloudExportGrant):
        raise CloudExportDenied("Cloud export requires a trusted, approved grant.")
    if cloud_export._backend_client is not None and cloud_export._backend_client is not client:
        raise CloudExportDenied("Cloud export grant does not match the provider client.")
    initial = admit_cloud_initial(
        cloud_export, user_input, previous_state=previous_response_id,
    )
    if instructions != initial.payload["instructions"]:
        raise CloudExportDenied("Unadmitted cloud instructions were supplied.")
    initial_request = admit_cloud_sdk_request(
        cloud_export, user_input, initial, model=MODEL, registry_tools=CLOUD_TOOLS,
    )
    cloud_export.consume("initial", user_input)
    try:
        response = client.responses.create(**initial_request.payload)
    except Exception:
        raise CloudExportDenied("Cloud provider request failed.") from None

    for item in response.output:
        if item.type == "function_call":
            print("[Tool] Cloud requested a bounded tool operation.")

            # Raw arguments are checked by the final registry boundary.
            # Malformed JSON/list payloads cannot silently become {}.
            scope = provider_tool_scope(
                "cloud", current_turn_authority(),
                [tool["name"] for tool in CLOUD_TOOLS],
            )
            try:
                with admitted_tools(scope):
                    tool_result = execute_tool(
                        item.name, item.arguments if item.arguments is not None else "{}"
                    )
            except Exception:
                raise CloudExportDenied("Cloud tool execution failed.") from None

            # The follow-up is a separate egress decision.  Do not emit the
            # executor's raw result or arbitrary exception/metadata fields.
            followup = admit_cloud_tool_followup(
                cloud_export, user_input, tool_name=item.name,
                tool_result=tool_result, call_id=item.call_id,
                response_id=response.id,
            )
            followup_request = admit_cloud_sdk_request(
                cloud_export, user_input, followup, model=MODEL,
                registry_tools=CLOUD_TOOLS,
            )
            cloud_export.consume("followup", user_input)
            try:
                final_response = client.responses.create(**followup_request.payload)
            except Exception:
                raise CloudExportDenied("Cloud provider follow-up failed.") from None

            return (
                final_response.output_text,
                final_response.id,
                None
            )

    return (
        response.output_text,
        response.id,
        None
    )