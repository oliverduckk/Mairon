from pathlib import Path
from typing import Optional

from core.evidence import (
    Evidence,
    EvidenceBundle,
)
from core.file_catalog import (
    get_approved_file_roots,
    is_path_within_approved_roots,
    is_safe_openable_file,
    search_local_files,
)
from core.workflow_result import (
    WorkflowResult,
)
from tools.file_tools import (
    open_approved_local_path,
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


def find_local_file(
    query: str,
) -> WorkflowResult:
    query = str(
        query
        or ""
    ).strip()

    matches = search_local_files(
        query
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
                    f'Core found one approved local file matching "{query}": '
                    f'{match["name"]}.'
                ),
                provenance="local_filesystem",
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
        matches[:5],
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

    A direct resolved_path is accepted only for Core-owned session referents and
    is still revalidated at both workflow and execution boundaries.
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

    if tool_result.get(
        "success"
    ) is not True:
        return WorkflowResult(
            success=False,
            status=(
                tool_result.get(
                    "status"
                )
                or "open_failed"
            ),
            error=(
                tool_result.get(
                    "message"
                )
                or (
                    f'I couldn\'t open {selected["name"]}.'
                )
            ),
            data={
                "selected_path": selected[
                    "path"
                ],
                "selected_name": selected[
                    "name"
                ],
                "tool_result": tool_result,
            },
        )

    evidence = EvidenceBundle(
        authority="desktop",
        success=True,
    )

    evidence.add(
        Evidence(
            claim=(
                f'Core verified and opened approved local file '
                f'{selected["name"]}.'
            ),
            provenance="local_filesystem",
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
            "tool_result": tool_result,
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

        result = open_approved_local_path(
            str(
                path.resolve()
            )
        )

        if result.get(
            "success"
        ) is not True:
            return WorkflowResult(
                success=False,
                status=(
                    result.get(
                        "status"
                    )
                    or "open_failed"
                ),
                error=(
                    result.get(
                        "message"
                    )
                    or f"I couldn't open {path.name}."
                ),
                data={
                    "opened": opened,
                    "failed_path": str(
                        path.resolve()
                    ),
                },
            )

        opened.append({
            "path": str(
                path.resolve()
            ),
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
                opened[-1][
                    "path"
                ]
                if opened
                else None
            ),
            "selected_name": (
                opened[-1][
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
    tool_result = open_approved_local_path(
        path
    )

    if tool_result.get(
        "success"
    ) is not True:
        return WorkflowResult(
            success=False,
            status=(
                tool_result.get(
                    "status"
                )
                or "open_failed"
            ),
            error=(
                tool_result.get(
                    "message"
                )
                or (
                    f"I couldn't open {display_name}."
                )
            ),
        )

    return WorkflowResult(
        success=True,
        status="folder_opened",
        answer_fact=(
            f"{display_name} is open."
        ),
        data={
            "selected_path": str(
                Path(
                    path
                ).resolve()
            ),
            "selected_name": display_name,
            "kind": "folder",
        },
    )
