from pathlib import Path
from typing import Optional

from core.desktop_agent_client import (
    open_approved_local_path_via_agent,
    search_approved_local_files_via_agent,
)
from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.file_catalog import (
    get_approved_file_roots,
    is_path_within_approved_roots,
    is_safe_openable_file,
)
from core.workflow_result import (
    WorkflowResult,
)


class DesktopAgentFileSearchError(
    RuntimeError
):
    def __init__(
        self,
        status: str,
        message: str,
    ):
        super().__init__(
            message
        )

        self.status = str(
            status
            or "file_search_failed"
        )

        self.message = str(
            message
            or "Local file search failed."
        )


def _relative_display_path(
    raw_path: str,
) -> str:
    path = Path(
        raw_path
    )

    roots = get_approved_file_roots()

    for root in roots:
        try:
            relative = path.resolve().relative_to(
                root.resolve()
            )

            if str(
                relative
            ) == ".":
                return root.name

            return (
                root.name
                + "\\"
                + str(
                    relative
                )
            )

        except Exception:
            continue

    return path.name


def _verify_agent_file_match(
    match,
) -> Optional[dict]:
    if not isinstance(
        match,
        dict,
    ):
        return None

    raw_path = str(
        match.get(
            "path",
            "",
        )
        or ""
    ).strip()

    if not raw_path:
        return None

    path = Path(
        raw_path
    )

    roots = get_approved_file_roots()

    if (
        not is_path_within_approved_roots(
            path,
            roots,
        )
        or not is_safe_openable_file(
            path,
            roots,
        )
    ):
        return None

    resolved = path.resolve()

    verified = dict(
        match
    )

    verified[
        "path"
    ] = str(
        resolved
    )

    verified[
        "name"
    ] = (
        str(
            match.get(
                "name",
                "",
            )
            or ""
        ).strip()
        or resolved.name
    )

    verified[
        "extension"
    ] = (
        str(
            match.get(
                "extension",
                "",
            )
            or ""
        ).strip().lower()
        or resolved.suffix.lower()
    )

    return verified


def search_local_files(
    query: str,
):
    """
    Compatibility-shaped Core wrapper around the Desktop Agent file search.

    The Agent performs Windows filesystem discovery. Core then independently
    re-validates every returned candidate against the approved roots and safe
    file policy before any candidate can enter conversation state.

    Existing deterministic tests may monkeypatch this function with the
    lower-level local catalogue search; production does not silently fall back.
    """

    query_value = str(
        query
        or ""
    ).strip()

    result = (
        search_approved_local_files_via_agent(
            query=query_value,
        )
    )

    if not isinstance(
        result,
        dict,
    ):
        raise DesktopAgentFileSearchError(
            status="unexpected_agent_result",
            message=(
                "The Windows Desktop Agent returned an unexpected local "
                "file-search result."
            ),
        )

    if result.get(
        "success"
    ) is not True:
        status = str(
            result.get(
                "status",
                "",
            )
            or "file_search_failed"
        ).strip()

        if status == "agent_unavailable":
            message = (
                "The Windows Desktop Agent isn't running, so I can't "
                "search your local files right now."
            )

        else:
            message = (
                result.get(
                    "message"
                )
                or "I couldn't search the approved local file roots."
            )

        raise DesktopAgentFileSearchError(
            status=(
                "desktop_agent_unavailable"
                if status == "agent_unavailable"
                else status
            ),
            message=message,
        )

    raw_matches = result.get(
        "matches",
        [],
    )

    if not isinstance(
        raw_matches,
        list,
    ):
        raise DesktopAgentFileSearchError(
            status="invalid_agent_search_result",
            message=(
                "The Windows Desktop Agent returned invalid file candidates."
            ),
        )

    verified = []

    for match in raw_matches:
        candidate = _verify_agent_file_match(
            match
        )

        if candidate is not None:
            verified.append(
                candidate
            )

    return verified


def open_approved_local_path(
    path: str,
):
    """
    Compatibility-shaped execution wrapper used by the workflows.

    Production routes through the Desktop Agent. Existing deterministic tests
    can monkeypatch this name without touching the transport layer.
    """

    return open_approved_local_path_via_agent(
        path=path,
    )


def _agent_confirmed_exact_path(
    result,
    expected_path: str,
) -> bool:
    if not isinstance(
        result,
        dict,
    ):
        return False

    actual = str(
        result.get(
            "path",
            "",
        )
        or ""
    ).strip()

    if not actual:
        return False

    try:
        actual_resolved = str(
            Path(
                actual
            ).resolve()
        )

        expected_resolved = str(
            Path(
                expected_path
            ).resolve()
        )

    except Exception:
        return False

    return (
        actual_resolved.lower()
        == expected_resolved.lower()
    )


def find_local_file(
    query: str,
) -> WorkflowResult:
    query = str(
        query
        or ""
    ).strip()

    try:
        matches = search_local_files(
            query
        )

    except DesktopAgentFileSearchError as exc:
        return WorkflowResult(
            success=False,
            status=exc.status,
            error=exc.message,
            data={
                "query": query,
                "matches": [],
            },
        )

    if not matches:
        return WorkflowResult(
            success=False,
            status="no_match",
            error=(
                f'I couldn\'t find an approved local file matching "{query}".'
            ),
            data={
                "query": query,
                "matches": [],
            },
        )

    if len(
        matches
    ) == 1:
        match = matches[
            0
        ]

        answer = (
            f'Found {match["name"]} in '
            f'{_relative_display_path(match["path"])}.'
        )

        evidence = EvidenceBundle(
            authority="desktop",
            success=True,
        )

        evidence.add(
            Evidence(
                claim=(
                    "The Windows Desktop Agent found one local file matching "
                    f'"{query}", and Core independently verified it is an '
                    f'approved file: {match["name"]}.'
                ),
                provenance="desktop_agent",
                confidence="verified",
                source_name=match[
                    "name"
                ],
                data={
                    "path": match[
                        "path"
                    ],
                    "query": query,
                },
            )
        )

        return WorkflowResult(
            success=True,
            status="unique_match",
            answer_fact=answer,
            evidence=evidence,
            data={
                "query": query,
                "matches": matches,
                "selected_path": match[
                    "path"
                ],
                "selected_name": match[
                    "name"
                ],
            },
        )

    lines = [
        f'I found {len(matches)} approved local files matching "{query}":'
    ]

    for index, match in enumerate(
        matches[
            :5
        ],
        start=1,
    ):
        lines.append(
            f'{index}. {match["name"]} — '
            f'{_relative_display_path(match["path"])}'
        )

    if len(
        matches
    ) > 5:
        lines.append(
            f"...and {len(matches) - 5} more."
        )

    return WorkflowResult(
        success=True,
        status="multiple_matches",
        answer_fact="\n".join(
            lines
        ),
        data={
            "query": query,
            "matches": matches,
            "selected_path": None,
        },
    )


def open_local_file(
    query: Optional[str] = None,
    resolved_path: Optional[str] = None,
) -> WorkflowResult:
    """
    Resolve and open one approved local file.

    Core owns the selected referent and validates it before execution.
    The Windows Desktop Agent validates it again before touching Windows.
    """

    selected = None

    if resolved_path:
        path = Path(
            resolved_path
        )

        roots = get_approved_file_roots()

        if (
            not is_path_within_approved_roots(
                path,
                roots,
            )
            or not is_safe_openable_file(
                path,
                roots,
            )
        ):
            return WorkflowResult(
                success=False,
                status="invalid_referent",
                error=(
                    "That remembered file is no longer an approved local file."
                ),
            )

        selected = {
            "path": str(
                path.resolve()
            ),
            "name": path.name,
        }

    else:
        result = find_local_file(
            str(
                query
                or ""
            )
        )

        if not result.success:
            return result

        if result.status != "unique_match":
            return WorkflowResult(
                success=True,
                status="multiple_matches",
                answer_fact=(
                    result.answer_fact
                    + "\nTell me which one you mean before I open anything."
                ),
                data=result.data,
            )

        selected = {
            "path": result.data[
                "selected_path"
            ],
            "name": result.data[
                "selected_name"
            ],
        }

    tool_result = open_approved_local_path(
        selected[
            "path"
        ]
    )

    if not isinstance(
        tool_result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_agent_result",
            error=(
                "The Windows Desktop Agent returned an unexpected local "
                "file-open result."
            ),
            data={
                "selected_path": selected[
                    "path"
                ],
                "selected_name": selected[
                    "name"
                ],
                "raw_result": str(
                    tool_result
                ),
            },
        )

    if tool_result.get(
        "success"
    ) is not True:
        result_status = str(
            tool_result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        if result_status == "agent_unavailable":
            status = "desktop_agent_unavailable"
            error = (
                "The Windows Desktop Agent isn't running, so I can't "
                f'open {selected["name"]} right now.'
            )

        else:
            status = (
                result_status
                or "open_failed"
            )

            error = (
                tool_result.get(
                    "message"
                )
                or (
                    f'I couldn\'t open {selected["name"]}.'
                )
            )

        return WorkflowResult(
            success=False,
            status=status,
            error=error,
            data={
                "selected_path": selected[
                    "path"
                ],
                "selected_name": selected[
                    "name"
                ],
                "agent_result": tool_result,
            },
        )

    if not _agent_confirmed_exact_path(
        tool_result,
        selected[
            "path"
        ],
    ):
        return WorkflowResult(
            success=False,
            status="file_open_confirmation_mismatch",
            error=(
                "The Windows Desktop Agent did not confirm the exact "
                "Core-approved file path, so I won't claim that file opened."
            ),
            data={
                "selected_path": selected[
                    "path"
                ],
                "selected_name": selected[
                    "name"
                ],
                "agent_result": tool_result,
            },
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                "Core verified the selected approved file and the Windows "
                f'Desktop Agent confirmed opening {selected["name"]}.'
            ),
            provenance="desktop_agent",
            confidence="verified",
            source_name=selected[
                "name"
            ],
            data={
                "path": selected[
                    "path"
                ],
            },
        )
    )

    return WorkflowResult(
        success=True,
        status="file_opened",
        answer_fact=(
            f'{selected["name"]} is open.'
        ),
        evidence=evidence,
        data={
            "selected_path": selected[
                "path"
            ],
            "selected_name": selected[
                "name"
            ],
            "agent_result": tool_result,
        },
    )


def select_local_file(
    resolved_path: str,
    display_name: Optional[str] = None,
) -> WorkflowResult:
    path = Path(
        str(
            resolved_path
            or ""
        )
    )

    roots = get_approved_file_roots()

    if (
        not is_path_within_approved_roots(
            path,
            roots,
        )
        or not is_safe_openable_file(
            path,
            roots,
        )
    ):
        return WorkflowResult(
            success=False,
            status="invalid_referent",
            error=(
                "That file is no longer an approved local file."
            ),
        )

    name = (
        str(
            display_name
            or ""
        ).strip()
        or path.name
    )

    return WorkflowResult(
        success=True,
        status="file_selected",
        answer_fact=(
            f"Selected {name}."
        ),
        data={
            "selected_path": str(
                path.resolve()
            ),
            "selected_name": name,
        },
    )


def open_local_files(
    resolved_paths,
) -> WorkflowResult:
    paths = [
        str(
            item
            or ""
        ).strip()
        for item in list(
            resolved_paths
            or []
        )
        if str(
            item
            or ""
        ).strip()
    ]

    if not paths:
        return WorkflowResult(
            success=False,
            status="invalid_referent",
            error=(
                "There aren't any approved files selected to open."
            ),
        )

    opened = []

    for raw_path in paths:
        path = Path(
            raw_path
        )

        roots = get_approved_file_roots()

        if (
            not is_path_within_approved_roots(
                path,
                roots,
            )
            or not is_safe_openable_file(
                path,
                roots,
            )
        ):
            return WorkflowResult(
                success=False,
                status="invalid_referent",
                error=(
                    "One of those files is no longer an approved local file."
                ),
            )

        resolved_path = str(
            path.resolve()
        )

        result = open_approved_local_path(
            resolved_path
        )

        if not isinstance(
            result,
            dict,
        ):
            return WorkflowResult(
                success=False,
                status="unexpected_agent_result",
                error=(
                    "The Windows Desktop Agent returned an unexpected "
                    "multi-file open result."
                ),
                data={
                    "opened": opened,
                    "failed_path": resolved_path,
                },
            )

        if result.get(
            "success"
        ) is not True:
            result_status = str(
                result.get(
                    "status",
                    "",
                )
                or ""
            ).strip()

            return WorkflowResult(
                success=False,
                status=(
                    "desktop_agent_unavailable"
                    if result_status == "agent_unavailable"
                    else (
                        result_status
                        or "open_failed"
                    )
                ),
                error=(
                    (
                        "The Windows Desktop Agent isn't running, so I "
                        "can't open those local files right now."
                    )
                    if result_status == "agent_unavailable"
                    else (
                        result.get(
                            "message"
                        )
                        or f"I couldn't open {path.name}."
                    )
                ),
                data={
                    "opened": opened,
                    "failed_path": resolved_path,
                    "agent_result": result,
                },
            )

        if not _agent_confirmed_exact_path(
            result,
            resolved_path,
        ):
            return WorkflowResult(
                success=False,
                status="file_open_confirmation_mismatch",
                error=(
                    "The Windows Desktop Agent did not confirm the exact "
                    "Core-approved file path."
                ),
                data={
                    "opened": opened,
                    "failed_path": resolved_path,
                    "agent_result": result,
                },
            )

        opened.append({
            "path": resolved_path,
            "name": path.name,
        })

    names = [
        item[
            "name"
        ]
        for item in opened
    ]

    if len(
        names
    ) == 1:
        answer = (
            f"{names[0]} is open."
        )

    elif len(
        names
    ) == 2:
        answer = (
            f"{names[0]} and {names[1]} are open."
        )

    else:
        answer = (
            f"Opened {len(names)} files."
        )

    return WorkflowResult(
        success=True,
        status="files_opened",
        answer_fact=answer,
        data={
            "opened": opened,
            "selected_path": (
                opened[
                    -1
                ][
                    "path"
                ]
                if opened
                else None
            ),
            "selected_name": (
                opened[
                    -1
                ][
                    "name"
                ]
                if opened
                else None
            ),
        },
    )


def open_trusted_folder(
    path: str,
    display_name: str,
) -> WorkflowResult:
    raw_path = str(
        path
        or ""
    ).strip()

    candidate = Path(
        raw_path
    )

    roots = get_approved_file_roots()

    if (
        not is_path_within_approved_roots(
            candidate,
            roots,
        )
        or not candidate.is_dir()
    ):
        return WorkflowResult(
            success=False,
            status="invalid_referent",
            error=(
                "That folder is no longer an approved local folder."
            ),
        )

    resolved_path = str(
        candidate.resolve()
    )

    tool_result = open_approved_local_path(
        resolved_path
    )

    if not isinstance(
        tool_result,
        dict,
    ):
        return WorkflowResult(
            success=False,
            status="unexpected_agent_result",
            error=(
                "The Windows Desktop Agent returned an unexpected folder-open "
                "result."
            ),
        )

    if tool_result.get(
        "success"
    ) is not True:
        result_status = str(
            tool_result.get(
                "status",
                "",
            )
            or ""
        ).strip()

        return WorkflowResult(
            success=False,
            status=(
                "desktop_agent_unavailable"
                if result_status == "agent_unavailable"
                else (
                    result_status
                    or "open_failed"
                )
            ),
            error=(
                (
                    "The Windows Desktop Agent isn't running, so I can't "
                    f"open {display_name} right now."
                )
                if result_status == "agent_unavailable"
                else (
                    tool_result.get(
                        "message"
                    )
                    or (
                        f"I couldn't open {display_name}."
                    )
                )
            ),
            data={
                "agent_result": tool_result,
            },
        )

    if not _agent_confirmed_exact_path(
        tool_result,
        resolved_path,
    ):
        return WorkflowResult(
            success=False,
            status="file_open_confirmation_mismatch",
            error=(
                "The Windows Desktop Agent did not confirm the exact "
                "Core-approved folder path."
            ),
            data={
                "agent_result": tool_result,
            },
        )

    return WorkflowResult(
        success=True,
        status="folder_opened",
        answer_fact=(
            f"{display_name} is open."
        ),
        data={
            "selected_path": resolved_path,
            "selected_name": display_name,
            "kind": "folder",
            "agent_result": tool_result,
        },
    )
