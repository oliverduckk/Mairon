import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


def run():
    provider_path = (
        SRC_DIR
        / "ai"
        / "ollama_provider.py"
    )

    source = provider_path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source
    )

    found_adaptive_branch = False
    found_valid_return = False

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.If,
        ):
            continue

        condition = ast.get_source_segment(
            source,
            node.test,
        ) or ""

        if (
            "core_intent == \"email_read\""
            not in condition
            or "should_skip_email_read_generation"
            not in condition
        ):
            continue

        found_adaptive_branch = True

        for child in node.body:
            if not isinstance(
                child,
                ast.Return,
            ):
                continue

            value = child.value

            assert isinstance(
                value,
                ast.Tuple,
            ), (
                "Adaptive Gmail provider return must preserve "
                "the provider's 4-value tuple contract."
            )

            assert len(
                value.elts
            ) == 4, (
                "Adaptive Gmail provider return must contain exactly "
                "4 values: response, conversation, cloud_request, "
                "pending_action."
            )

            found_valid_return = True

    assert found_adaptive_branch, (
        "Adaptive Gmail fast-return branch was not found."
    )

    assert found_valid_return, (
        "Adaptive Gmail fast-return branch has no valid 4-value return."
    )

    print(
        "Mairon Phase 8.7.7.1 provider return-contract tests: PASS"
    )


if __name__ == "__main__":
    run()
