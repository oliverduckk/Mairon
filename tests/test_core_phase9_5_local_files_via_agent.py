import sys
import tempfile
import threading
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


import core.desktop_agent_client as agent_client
import core.file_catalog as file_catalog
import core.workflows.file_actions as file_workflow

from core.desktop_agent_protocol import (
    build_request,
    validate_request,
)
from desktop_agent import (
    create_desktop_agent_server,
)


def run():
    # --------------------------------------------------
    # 1. Protocol admits only bounded query/path arguments.
    # --------------------------------------------------

    search_request = validate_request(
        build_request(
            request_id="phase9-5-search",
            action="search_approved_local_files",
            args={
                "query": "resume",
            },
        )
    )

    assert search_request[
        "args"
    ] == {
        "query": "resume",
    }

    open_request = validate_request(
        build_request(
            request_id="phase9-5-open",
            action="open_approved_local_path",
            args={
                "path": r"C:\Users\Test\Documents\resume.pdf",
            },
        )
    )

    assert open_request[
        "args"
    ][
        "path"
    ].endswith(
        "resume.pdf"
    )

    for action, args in (
        (
            "search_approved_local_files",
            {
                "query": "resume",
                "command": "whoami",
            },
        ),
        (
            "open_approved_local_path",
            {
                "path": r"C:\test.pdf",
                "shell": "powershell",
            },
        ),
    ):
        try:
            validate_request({
                "version": "1",
                "request_id": (
                    "phase9-5-reject-"
                    + action
                ),
                "action": action,
                "args": args,
            })

        except ValueError:
            pass

        else:
            raise AssertionError(
                f"{action} accepted an arbitrary execution argument."
            )

    # --------------------------------------------------
    # 2. Workflow search/open crosses authenticated Agent boundary.
    # --------------------------------------------------

    original_catalog_roots = (
        file_catalog.get_approved_file_roots
    )

    original_workflow_roots = (
        file_workflow.get_approved_file_roots
    )

    original_url = (
        agent_client.get_desktop_agent_url
    )

    original_secret = (
        agent_client.load_or_create_agent_secret
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(
            temp_dir
        ).resolve()

        resume = (
            root
            / "Oliver Resume.pdf"
        )

        resume.write_bytes(
            b"%PDF-test"
        )

        roots = [
            root
        ]

        file_catalog.get_approved_file_roots = (
            lambda: list(
                roots
            )
        )

        file_workflow.get_approved_file_roots = (
            lambda: list(
                roots
            )
        )

        calls = []

        def fake_executor(
            action,
            args,
        ):
            calls.append(
                (
                    action,
                    dict(
                        args
                    ),
                )
            )

            if action == "search_approved_local_files":
                return {
                    "success": True,
                    "status": "search_completed",
                    "query": args[
                        "query"
                    ],
                    "count": 1,
                    "matches": [
                        {
                            "path": str(
                                resume
                            ),
                            "name": resume.name,
                            "extension": ".pdf",
                            "root": str(
                                root
                            ),
                            "root_priority": 0,
                            "depth": 0,
                            "score": 100,
                        }
                    ],
                }

            if action == "open_approved_local_path":
                return {
                    "success": True,
                    "status": "file_opened",
                    "path": args[
                        "path"
                    ],
                    "application": "default",
                }

            raise AssertionError(
                "Unexpected Phase 9.5 action reached Agent executor."
            )

        secret = (
            "phase9-5-test-secret-"
            "abcdefghijklmnopqrstuvwxyz012345"
        )

        server = create_desktop_agent_server(
            host="127.0.0.1",
            port=0,
            secret=secret,
            action_executor=fake_executor,
        )

        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={
                "poll_interval": 0.05,
            },
            daemon=True,
        )

        thread.start()

        try:
            host, port = (
                server.server_address
            )

            agent_client.get_desktop_agent_url = (
                lambda: f"http://{host}:{port}"
            )

            agent_client.load_or_create_agent_secret = (
                lambda: secret
            )

            found = file_workflow.find_local_file(
                "resume"
            )

            assert found.success is True
            assert found.status == "unique_match"

            assert found.data[
                "selected_path"
            ] == str(
                resume.resolve()
            )

            opened = file_workflow.open_local_file(
                resolved_path=str(
                    resume
                )
            )

            assert opened.success is True
            assert opened.status == "file_opened"

            assert opened.answer_fact == (
                "Oliver Resume.pdf is open."
            )

            assert calls == [
                (
                    "search_approved_local_files",
                    {
                        "query": "resume",
                    },
                ),
                (
                    "open_approved_local_path",
                    {
                        "path": str(
                            resume.resolve()
                        ),
                    },
                ),
            ]

            assert (
                opened.evidence.evidence[
                    0
                ].provenance
                == "desktop_agent"
            )

        finally:
            server.shutdown()
            server.server_close()

            thread.join(
                timeout=2.0
            )

            agent_client.get_desktop_agent_url = (
                original_url
            )

            agent_client.load_or_create_agent_secret = (
                original_secret
            )

            file_catalog.get_approved_file_roots = (
                original_catalog_roots
            )

            file_workflow.get_approved_file_roots = (
                original_workflow_roots
            )

    # --------------------------------------------------
    # 3. Core refuses an Agent-returned candidate outside approved roots.
    # --------------------------------------------------

    original_search = (
        file_workflow
        .search_approved_local_files_via_agent
    )

    try:
        with tempfile.TemporaryDirectory() as approved_dir:
            approved_root = Path(
                approved_dir
            ).resolve()

            file_workflow.get_approved_file_roots = (
                lambda: [
                    approved_root
                ]
            )

            file_workflow.search_approved_local_files_via_agent = (
                lambda query: {
                    "success": True,
                    "status": "search_completed",
                    "matches": [
                        {
                            "path": r"C:\Windows\System32\cmd.exe",
                            "name": "cmd.exe",
                            "extension": ".exe",
                        }
                    ],
                }
            )

            matches = file_workflow.search_local_files(
                "cmd"
            )

            assert matches == []

    finally:
        file_workflow.search_approved_local_files_via_agent = (
            original_search
        )

        file_workflow.get_approved_file_roots = (
            original_workflow_roots
        )

    # --------------------------------------------------
    # 4. Agent outage fails honestly; no local search fallback.
    # --------------------------------------------------

    original_search = (
        file_workflow
        .search_approved_local_files_via_agent
    )

    try:
        file_workflow.search_approved_local_files_via_agent = (
            lambda query: {
                "success": False,
                "status": "agent_unavailable",
                "message": (
                    "Mairon Desktop Agent is not reachable."
                ),
            }
        )

        unavailable = file_workflow.find_local_file(
            "resume"
        )

        assert unavailable.success is False

        assert unavailable.status == (
            "desktop_agent_unavailable"
        )

        assert (
            "Desktop Agent isn't running"
            in unavailable.error
        )

    finally:
        file_workflow.search_approved_local_files_via_agent = (
            original_search
        )

    print(
        "Mairon Phase 9.5 local-file agent routing tests: PASS"
    )


if __name__ == "__main__":
    run()
