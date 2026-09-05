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

    target_if = None

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.If,
        ):
            continue

        condition = (
            ast.get_source_segment(
                source,
                node.test,
            )
            or ""
        )

        if (
            'core_intent == "email_read"'
            in condition
            and "should_skip_email_read_generation"
            in condition
        ):
            target_if = node
            break

    assert target_if is not None, (
        "Adaptive Gmail fast path was not found."
    )

    working_assignment_index = None
    assistant_append_index = None
    return_index = None

    for index, statement in enumerate(
        target_if.body
    ):
        if isinstance(
            statement,
            ast.Assign,
        ):
            for target in statement.targets:
                if (
                    isinstance(
                        target,
                        ast.Name,
                    )
                    and target.id
                    == "working_conversation"
                ):
                    working_assignment_index = index

        if isinstance(
            statement,
            ast.Expr,
        ):
            segment = (
                ast.get_source_segment(
                    source,
                    statement,
                )
                or ""
            )

            if (
                "working_conversation.append"
                in segment
                and '"role": "assistant"'
                in segment
                and "final_response_text"
                in segment
            ):
                assistant_append_index = index

        if isinstance(
            statement,
            ast.Return,
        ):
            return_index = index

            assert isinstance(
                statement.value,
                ast.Tuple,
            )

            assert len(
                statement.value.elts
            ) == 4

    assert working_assignment_index is not None, (
        "Adaptive Gmail path must initialise working_conversation."
    )

    assert assistant_append_index is not None, (
        "Adaptive Gmail path must commit the verified assistant response "
        "to live conversation state."
    )

    assert return_index is not None, (
        "Adaptive Gmail path has no return."
    )

    assert (
        working_assignment_index
        < assistant_append_index
        < return_index
    ), (
        "Adaptive Gmail conversation state must be initialised and committed "
        "before the provider returns."
    )

    print(
        "Mairon Phase 8.7.7.2 fast-email conversation-commit tests: PASS"
    )


if __name__ == "__main__":
    run()
