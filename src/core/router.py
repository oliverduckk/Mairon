def parse_cloud_command(user_input):
    """
    Check whether Oliver explicitly requested cloud processing with /cloud.
    """

    if user_input.lower() == "/cloud":
        return True, ""

    if user_input.lower().startswith("/cloud "):
        return True, user_input[7:].strip()

    return False, user_input


def route_message(
    user_input,
    local_ai,
    cloud_ai,
    instructions,
    local_state,
    cloud_state
):
    """
    Route a message to either Mairon's local or cloud AI provider.

    Local processing is always the default.
    Cloud processing currently requires an explicit /cloud command.
    """

    use_cloud, clean_input = parse_cloud_command(user_input)

    if use_cloud:
        if not clean_input:
            return (
                "You invoked the cloud and then gave me nothing to do. Impressive.",
                local_state,
                cloud_state
            )

        if cloud_ai is None:
            return (
                "Cloud processing is currently unavailable.",
                local_state,
                cloud_state
            )

        print("[AI] Using cloud: GPT-5.6 Luna")

        answer, cloud_state = cloud_ai["module"].get_response(
            cloud_ai["client"],
            clean_input,
            instructions,
            cloud_state
        )

        return answer, local_state, cloud_state

    print("[AI] Using local: Qwen3 14B")

    answer, local_state = local_ai["module"].get_response(
        local_ai["client"],
        clean_input,
        instructions,
        local_state
    )

    return answer, local_state, cloud_state