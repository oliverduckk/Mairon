from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.evidence import EvidenceBundle
from core.epistemic_router import EpistemicRoute
from core.turn_state import TurnState


@dataclass
class AnswerContract:
    """
    Contract passed to the language layer after Core has decided the task.

    Qwen may phrase the result, but it does not get to redefine the facts,
    tool result, established state, or requested task.
    """

    task: str
    speech_act: str
    intent: str
    subject: Optional[str]

    authority: str
    epistemic_mode: str

    required_claims: List[str] = field(
        default_factory=list
    )
    forbidden_behaviours: List[str] = field(
        default_factory=list
    )

    allow_recommendations: bool = False
    allow_new_factual_claims: bool = False
    allow_follow_up_question: bool = False

    evidence: Optional[EvidenceBundle] = None

    resolved_referents: Dict[str, str] = field(
        default_factory=dict
    )

    metadata: Dict[str, str] = field(
        default_factory=dict
    )

    def to_model_instruction(
        self,
    ) -> str:
        lines = [
            "CORE ANSWER CONTRACT:",
            f"Task: {self.task}",
            f"Speech act: {self.speech_act}",
            f"Intent: {self.intent}",
            f"Subject: {self.subject or 'none'}",
            f"Factual authority: {self.authority}",
            f"Epistemic mode: {self.epistemic_mode}",
        ]

        if self.resolved_referents:
            lines.extend([
                "",
                "RESOLVED CONVERSATION REFERENCES:",
            ])

            for pronoun, referent in self.resolved_referents.items():
                lines.append(
                    f"- {pronoun!r} refers to: {referent}"
                )

        lines.extend([
            "",
            "REQUIRED CLAIMS:",
        ])

        if self.required_claims:
            lines.extend(
                "- "
                + claim
                for claim in self.required_claims
            )
        else:
            lines.append(
                "- none"
            )

        lines.extend([
            "",
            "BEHAVIOURAL LIMITS:",
            (
                "- Recommendations allowed: "
                + str(
                    self.allow_recommendations
                ).lower()
            ),
            (
                "- New unsupported factual claims allowed: "
                + str(
                    self.allow_new_factual_claims
                ).lower()
            ),
            (
                "- Follow-up question allowed: "
                + str(
                    self.allow_follow_up_question
                ).lower()
            ),
        ])

        for item in self.forbidden_behaviours:
            lines.append(
                "- FORBIDDEN: "
                + item
            )

        if self.evidence:
            lines.extend([
                "",
                "VERIFIED EVIDENCE:",
            ])

            if not self.evidence.evidence:
                lines.append(
                    "- none"
                )

            for item in self.evidence.evidence:
                lines.append(
                    "- "
                    + item.claim
                    + " "
                    + (
                        f"[{item.provenance}; {item.confidence}]"
                    )
                )

            if self.evidence.uncertainty:
                lines.append(
                    "- Uncertainty: "
                    + self.evidence.uncertainty
                )

        if not self.allow_new_factual_claims:
            lines.extend([
                "",
                "FACTUAL GROUNDING POLICY:",
                "- Specific factual claims must come from Oliver's current message, "
                "recent user-provided context, resolved references in this contract, "
                "required claims, or verified Core evidence.",
                "- Do not use model training memory to add product properties, technical "
                "specifications, itinerary details, location assumptions, media facts, "
                "history, or other external facts.",
                "- Plausible is not the same as grounded.",
                "- Subjective reaction and clearly non-literal banter are allowed only "
                "when they do not depend on an unsupported factual premise.",
                "- Prefer a shorter response over adding an ungrounded detail.",
            ])

        lines.extend([
            "",
            "LANGUAGE POLICY:",
            "- English is the default response language.",
            "- A foreign-language phrase may be used only as a rare, very short joke.",
            "- Never switch a full sentence or paragraph into another language unless "
            "Oliver explicitly asks.",
            "- Oliver should not need to understand Chinese, Japanese, or another "
            "language to understand the response.",
            "",
            "Do not contradict this contract. Do not add factual detail "
            "that Core has not supplied when new factual claims are forbidden.",
        ])

        return "\n".join(
            lines
        )


def build_answer_contract(
    turn: TurnState,
    route: EpistemicRoute,
    evidence: Optional[EvidenceBundle] = None,
) -> AnswerContract:
    """
    Generic contract. Workflows may add required claims after obtaining
    authoritative results.
    """

    contract = AnswerContract(
        task=(
            turn.requested_action
            or turn.intent
            or "respond"
        ),
        speech_act=turn.speech_act,
        intent=turn.intent,
        subject=turn.subject,
        authority=route.authority,
        epistemic_mode=route.mode,
        allow_recommendations=turn.should_recommend,
        allow_new_factual_claims=(
            route.mode
            in {
                "conversation",
                "subjective",
                "classify_then_verify",
            }
        ),
        allow_follow_up_question=(
            turn.should_continue_conversation
            and turn.speech_act
            not in {
                "thanks",
                "request_action",
            }
        ),
        evidence=evidence,
        resolved_referents=dict(
            turn.resolved_referents
        ),
    )

    if turn.intent == "order_status":
        contract.allow_recommendations = False
        contract.allow_new_factual_claims = False
        contract.allow_follow_up_question = False

        contract.forbidden_behaviours.extend([
            "Do not dump unrelated inbox messages.",
            "Do not recommend contacting the retailer if Gmail already answers the question.",
            "Do not claim an order status that is not present in the Gmail evidence.",
            "Do not offer unrelated next steps after answering the status.",
        ])

    if turn.intent == "factual_question":
        contract.allow_recommendations = False
        contract.forbidden_behaviours.extend([
            "Answer the current factual question directly and truthfully before doing anything conversational.",
            "Do not intentionally give a fake/joke factual answer first and then retract or correct it.",
            "A very short personality line may follow the answer only when it is directly about the current question, does not contradict the answer, and adds no unsupported Oliver/Mairon history.",
            "Do not append callbacks to unrelated prior topics after the factual answer.",
            "Do not revive an old product, device, trip, joke, or assistant phrase merely "
            "because it appears in conversation history.",
        ])

    if turn.intent == "share_context":
        contract.allow_recommendations = False
        contract.allow_new_factual_claims = False
        contract.allow_follow_up_question = False
        contract.forbidden_behaviours.extend([
            "Do not turn a declarative share into unsolicited recommendations.",
            "Do not infer that Oliver is asking for advice merely because the topic "
            "is something advice could be given about.",
            "React only to what Oliver actually said and the immediately active conversation.",
            "Do not revive unrelated older topics from retrieved history.",
            "Do not manufacture a problem to solve.",
            "Do not invent plausible details merely to make the reaction more colourful.",
            "Do not offer another task after reacting to the update.",
            "Keep the response conversational and compact; normally one to three sentences.",
        ])

    if turn.intent == "acknowledge":
        contract.allow_recommendations = False
        contract.allow_follow_up_question = False
        contract.allow_new_factual_claims = False

        contract.forbidden_behaviours.extend([
            "Do not turn thanks into another offer of help.",
            "Do not append generic customer-service follow-up language.",
            "Do not answer or revive an older question or topic.",
            "Do not introduce factual claims.",
            "Keep a simple acknowledgement brief; normally one short sentence.",
        ])

    if turn.intent == "casual_conversation":
        contract.allow_recommendations = False
        contract.allow_new_factual_claims = False
        contract.forbidden_behaviours.extend([
            "Keep banter anchored to the live conversation.",
            "Do not turn prior Mairon inventions into factual conversation history.",
            "Do not import unrelated long-term conversation material.",
        ])

    if turn.intent == "self_correction":
        contract.allow_recommendations = False
        contract.allow_new_factual_claims = False
        contract.allow_follow_up_question = False
        contract.forbidden_behaviours.extend([
            "Treat Oliver's latest explicit correction as authoritative for what he meant.",
            "Do not argue with the correction.",
            "Do not describe the correction as Mairon being fact-checked.",
            "Do not revive the superseded user detail as though it were still current.",
        ])

    if turn.intent == "conversation_recall":
        contract.allow_recommendations = False
        contract.allow_new_factual_claims = False
        contract.allow_follow_up_question = False
        contract.forbidden_behaviours.extend([
            "Answer only from the supplied live conversation record.",
            "Do not use web research, media research, model memory, or unrelated journal history.",
            "Prior Mairon statements are not proof of user facts.",
            "When Oliver explicitly corrected an earlier statement, prefer the later correction.",
            "If the live conversation does not contain the answer, say so rather than guessing.",
        ])

    return contract
