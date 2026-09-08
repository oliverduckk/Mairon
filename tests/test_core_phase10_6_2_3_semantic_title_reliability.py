import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from continuity.chat_title_generator import generate_semantic_chat_title


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeResponse:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _ThinkingSensitiveClient:
    """
    Simulates the live failure shape we care about: a tiny generation budget
    produces no usable visible content unless thinking is explicitly disabled.
    """

    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)

        if kwargs.get("think") is not False:
            return _FakeResponse("")

        return _FakeResponse("DNS Overview")


def run():
    # --------------------------------------------------
    # 1. Semantic title generation explicitly disables model thinking.
    # --------------------------------------------------

    client = _ThinkingSensitiveClient()

    title = generate_semantic_chat_title(
        local_ai={
            "name": "ollama",
            "client": client,
        },
        model_name="qwen3.5:9b",
        user_text="Explain how DNS works.",
        assistant_text=(
            "DNS maps human-readable domain names to IP addresses using a "
            "hierarchy of resolvers and authoritative name servers."
        ),
    )

    assert title == "DNS Overview"
    assert len(client.calls) == 1

    call = client.calls[0]
    assert call.get("think") is False
    assert call["options"]["num_predict"] == 24
    assert "tools" not in call

    # The isolated title call still receives only the first user/assistant turn.
    assert len(call["messages"]) == 2
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["role"] == "user"

    # --------------------------------------------------
    # 2. The live async path exposes enough diagnostics to identify where a
    #    future title failure occurs instead of silently leaving the fallback.
    # --------------------------------------------------

    service_path = SRC_DIR / "application_service.py"
    service_source = service_path.read_text(encoding="utf-8")

    ast.parse(service_source, filename=str(service_path))

    required_diagnostics = (
        "[Session] Semantic title queued.",
        "[Session] Semantic title generation started.",
        "[Session] Semantic title generation returned no usable title.",
        "[Session] Semantic title was generated but not applied;",
        "[Session] Semantic title: ",
    )

    for diagnostic in required_diagnostics:
        assert diagnostic in service_source

    # Generation remains asynchronous so first-response latency is unaffected.
    assert "threading.Thread(" in service_source
    assert "daemon=True" in service_source

    # --------------------------------------------------
    # 3. Regression guard: do not solve semantic titles by replacing the
    #    model-generated title with more first-message heuristics.
    # --------------------------------------------------

    generator_path = SRC_DIR / "continuity" / "chat_title_generator.py"
    generator_source = generator_path.read_text(encoding="utf-8")

    ast.parse(generator_source, filename=str(generator_path))

    assert "think=False" in generator_source
    assert "FIRST USER MESSAGE:" in generator_source
    assert "FIRST ASSISTANT RESPONSE:" in generator_source

    print(
        "Mairon Phase 10.6.2.3 semantic-title reliability tests: PASS"
    )


if __name__ == "__main__":
    run()
