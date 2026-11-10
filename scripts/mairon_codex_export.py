#!/usr/bin/env python3
"""Create a reviewable, source-only Mairon export for an isolated Codex workspace.

The exporter never edits the original project, sends nothing to Codex, and does
not provide operating-system isolation. Human review is mandatory.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import ipaddress
import json
import re
import sys
import tokenize
from datetime import datetime
from pathlib import Path, PurePosixPath

# Deliberately narrow. These are the S1 authority/contract/provider handoff files,
# not the entire application. Extras must be explicitly requested with --add.
S1_REQUIRED = (
    "src/application_service.py",
    "src/core/orchestrator.py",
    "src/core/router.py",
    "src/core/answer_contract.py",
    "src/core/answer_contract_runtime.py",
    "src/ai/ollama_provider.py",
    "src/ai/openai_provider.py",
    "src/ai/provider.py",
)

# Useful context/test files from the reviewed S1 blueprint. Missing optional
# paths are reported, never silently replaced by fabricated files.
S1_OPTIONAL = (
    "src/main.py",
    "src/core/conversation_state.py",
    "src/core/critical_response_safety.py",
    "tests/test_core_phase10_1_application_service.py",
    "tests/test_core_milestone3b2b_bounded_publication.py",
    "tests/test_core_milestone3b3a_public_shadow_integration.py",
)

DENIED_PARTS = {
    ".git", ".venv", ".vscode", "__pycache__", "private", "data",
    "assets", "benchmarks", "docs", "secrets", "credentials", "backup", "backups", "personal", "userdata", "user_data", "logs", "log", "cache", "caches", "exports", "output", "outputs",
}
MAX_FILE_BYTES = 2_500_000
MAX_TOTAL_BYTES_S1 = 12_000_000
MAX_TOTAL_BYTES_CODEBASE = 80_000_000
MAX_FILE_COUNT_CODEBASE = 2500
CODEBASE_ROOT_METADATA = ("Mairon.pyw", "requirements.txt", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini")
SOURCE_SUFFIXES = {".py", ".pyw"}

EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+\-]+@([A-Z0-9.\-]+\.[A-Z]{2,})\b")
KNOWN_TEST_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "test.org", "test.invalid"}
PERSONAL_NAME = re.compile(r"(?i)\boliver(?:duck+k)?\b")
# A made-up replacement that is used consistently in exported examples/prompts.
PSEUDONYM = "SampleUser"
IPV4_CANDIDATE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
RFC1918 = tuple(ipaddress.IPv4Network(network) for network in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))
PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("credential-like token", re.compile(r"(?:sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_\-]{25,}|xox[baprs]-[A-Za-z0-9-]{12,})")),
    ("literal credential assignment", re.compile(r"(?i)^\s*(?:[A-Za-z_]\w*\.)?(?:api_key|secret|client_secret|access_token|refresh_token|password|auth_token|private_key)\s*(?::\s*\w+\s*)?=\s*(?:[rRuUbBfF]{0,2})['\"][^'\"\n]{4,}['\"]")),
    ("Windows user profile path", re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s'\"]+")),
    ("Unix user home path", re.compile(r"(?i)(?:/Users/|/home/)[A-Za-z0-9_.-]+")),
    ("personal name/handle to inspect", re.compile(r"(?i)\boliver(?:duck+k)?\b")),
)


def safe_path(label: str, scope: str = "s1") -> Path:
    # Reject arbitrary places such as .env, other users' home directories, or
    # alternate stream syntax. Export only approved code and build metadata.
    if "\\" in label or ":" in label or label.startswith("/"):
        raise ValueError(f"Unsafe path syntax: {label!r}")
    path = PurePosixPath(label)
    if (
        path.is_absolute() or ".." in path.parts or "." in path.parts
        or not path.parts or any(part.lower() in DENIED_PARTS or part.startswith(".") for part in path.parts)
    ):
        raise ValueError(f"Not an approved export path: {label!r}")
    source_path = (path.parts[0] in ("src", "tests")
                   or (scope == "codebase" and path.parts[0] == "scripts"))
    if source_path and path.suffix.lower() in SOURCE_SUFFIXES and len(path.parts) >= 2:
        return Path(*path.parts)
    if scope == "codebase" and len(path.parts) == 1 and path.name in CODEBASE_ROOT_METADATA:
        return Path(*path.parts)
    raise ValueError(f"Not an approved {scope} source/metadata path: {label!r}")


def codebase_labels(repo: Path) -> tuple[list[str], list[str]]:
    """Discover current Python sources/tests/scripts without following reparse points.

    Reject unsafe Python links rather than silently leaking via an external target.
    Markdown, fixtures, credentials, private runtime state and non-code assets are
    intentionally not exported merely because they reside under a code directory.
    """
    labels: list[str] = []
    exclusions: list[str] = []
    for folder in ("src", "tests", "scripts"):
        root = repo / folder
        if not root.exists():
            continue
        if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
            raise ValueError(f"Source root is a symlink/junction: {folder}")
        # pathlib.rglob does not follow symlinked directories by default; each
        # selected path also passes no_symlinks() immediately before reading.
        for candidate in root.rglob("*"):
            try:
                relative = candidate.relative_to(repo)
            except ValueError:
                raise ValueError("Discovered source path escaped repository") from None
            parts = relative.parts
            if any(part.lower() in DENIED_PARTS or part.startswith(".") for part in parts):
                continue
            if candidate.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if candidate.name.lower().startswith("mairon_codex_export"):
                exclusions.append(relative.as_posix())
                continue
            if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
                raise ValueError(f"Code path is a symlink/junction: {relative.as_posix()}")
            if not candidate.is_file():
                continue
            labels.append(relative.as_posix())
    for name in CODEBASE_ROOT_METADATA:
        if (repo / name).is_file():
            labels.append(name)
    labels = sorted(set(labels))
    if len(labels) > MAX_FILE_COUNT_CODEBASE:
        raise ValueError(f"Discovered {len(labels)} files; limit is {MAX_FILE_COUNT_CODEBASE}")
    return labels, exclusions


def no_symlinks(repo: Path, relative: Path) -> Path:
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"Symlink/junction-like path not allowed: {relative.as_posix()}")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(repo):
        raise ValueError(f"Path escapes repo: {relative.as_posix()}")
    if not resolved.is_file():
        raise ValueError(f"Not a regular file: {relative.as_posix()}")
    return resolved


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _name_rewrite_spans(text: str) -> list[tuple[int, int]]:
    """Only replace names inside string literals / docstrings / comments.

    Fail closed on identifiers, f-string expressions or syntactically invalid
    Python instead of rewriting executable names.
    """
    offsets = _line_offsets(text)
    safe_spans: list[tuple[int, int]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError(f"Cannot tokenise source for copy-only substitution: {exc}") from exc
    allowed = {tokenize.STRING, tokenize.COMMENT}
    if hasattr(tokenize, "FSTRING_MIDDLE"):
        allowed.add(tokenize.FSTRING_MIDDLE)
    for token in tokens:
        if token.type not in allowed:
            continue
        begin = offsets[token.start[0] - 1] + token.start[1]
        end = offsets[token.end[0] - 1] + token.end[1]
        safe_spans.append((begin, end))
    return safe_spans


def pseudonymize_copy(text: str, label: str) -> tuple[str, int]:
    """Produce a pseudonymised copy; NEVER modify source files."""
    hits = list(PERSONAL_NAME.finditer(text))
    if not hits:
        return text, 0
    spans = _name_rewrite_spans(text)
    unsafe = [m for m in hits if not any(start <= m.start() and m.end() <= end for start, end in spans)]
    if unsafe:
        raise ValueError(
            f"{label}: {len(unsafe)} personal-name references in executable tokens; "
            "review manually rather than renaming identifiers"
        )
    new = PERSONAL_NAME.sub(PSEUDONYM, text)
    try:
        old_ast = ast.parse(text, filename=label)
        new_ast = ast.parse(new, filename=label)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"{label}: sanitised Python failed syntax validation: {exc}") from exc

    class HideStringConstants(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                return ast.copy_location(ast.Constant(value="[string]"), node)
            return node

    if ast.dump(HideStringConstants().visit(old_ast), include_attributes=False) != ast.dump(
        HideStringConstants().visit(new_ast), include_attributes=False
    ):
        raise ValueError(f"{label}: substitution altered executable AST structure")
    return new, len(hits)


def is_private_ipv4_text(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in RFC1918)


def scan_text(text: str) -> list[str]:
    issues: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pattern in PATTERNS:
            if pattern.search(line):
                issues.append(f"line {n}: {name}")
        for match in IPV4_CANDIDATE.finditer(line):
            if is_private_ipv4_text(match.group(0)):
                # A source comment's version label (e.g. Phase 10.7.10.1)
                # is not a network address.
                before = line[:match.start()]
                if not re.search(r"(?i)#\s*phase\s*$", before):
                    issues.append(f"line {n}: private network address")
        for match in EMAIL.finditer(line):
            if match.group(1).lower() not in KNOWN_TEST_DOMAINS:
                issues.append(f"line {n}: email address (non-example domain)")
    return issues


def decode_selected_text(raw: bytes, relative: Path) -> tuple[str, str, bool]:
    """Decode selected text; transcode BOM-marked UTF-16 *metadata only*.

    The repository can contain a PowerShell-written UTF-16 requirements.txt.
    NUL bytes there are encoding bytes, not proof of binary content. Only an
    explicit UTF-16 BOM permits this exception, and Python source remains
    subject to the stricter UTF-8-only check.
    """
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        if relative.as_posix() not in CODEBASE_ROOT_METADATA:
            raise ValueError(
                f"UTF-16 only supported for approved root metadata: {relative.as_posix()}"
            )
        try:
            contents = raw.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Malformed UTF-16 metadata: {relative.as_posix()}") from exc
        encoding = "utf-16-le" if raw.startswith(b"\xff\xfe") else "utf-16-be"
        converted = True
    else:
        if b"\x00" in raw:
            raise ValueError(f"Binary content detected: {relative.as_posix()}")
        try:
            contents = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Non-UTF-8 source requires manual review: {relative.as_posix()}"
            ) from exc
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        converted = False
    if any(ord(character) < 32 and character not in "\t\n\r" for character in contents):
        raise ValueError(f"Unexpected control characters: {relative.as_posix()}")
    return contents, encoding, converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Path to the original Mairon repository")
    parser.add_argument("--scope", choices=("s1", "codebase"), default="s1", help="s1: 14-file selection; codebase: all src/tests/scripts Python plus approved root build metadata")
    parser.add_argument("--out", type=Path, help="New, empty export folder OUTSIDE the repository")
    parser.add_argument("--add", action="append", default=[], metavar="SRC_OR_TEST_PY", help="Explicit extra repo-relative .py file (repeatable)")
    parser.add_argument("--scan-only", action="store_true", help="Inspect selected source files; do not create an export")
    parser.add_argument("--omit-flagged-tests", action="store_true", help="Only in codebase mode: omit whole test files flagged by the privacy scan; never omit flagged source/scripts/metadata")
    parser.add_argument("--pseudonymize", action="store_true", help="Replace the known personal name/handle ONLY in copy string literals and comments; never original source")
    args = parser.parse_args()

    try:
        if args.omit_flagged_tests and args.scope != "codebase":
            raise ValueError("--omit-flagged-tests requires --scope codebase")
        repo = args.repo.expanduser().resolve(strict=True)
        if not repo.is_dir() or not (repo / "src").is_dir():
            raise ValueError("--repo must point to the Mairon project directory containing src/")

        if args.out is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            prefix = "S1" if args.scope == "s1" else "Codebase"
            output = repo.parent / "Mairon-Codex-Exports" / f"{prefix}-{stamp}"
        else:
            output = args.out.expanduser().resolve(strict=False)
        output = output.resolve(strict=False)
        if output == repo or output.is_relative_to(repo):
            raise ValueError("Output MUST be outside the real Mairon repository")
        if output.exists():
            raise ValueError(f"Output already exists; refusing to overwrite: {output}")

        if args.scope == "codebase":
            discovered, export_tool_exclusions = codebase_labels(repo)
            labels = list(dict.fromkeys((*discovered, *args.add)))
            required = set(labels)
        else:
            labels = list(dict.fromkeys((*S1_REQUIRED, *S1_OPTIONAL, *args.add)))
            required = set(S1_REQUIRED) | set(args.add)
            export_tool_exclusions = []
        byte_limit = MAX_TOTAL_BYTES_CODEBASE if args.scope == "codebase" else MAX_TOTAL_BYTES_S1
        items: list[tuple[Path, bytes, str, int, str, bool]] = []
        optional_missing: list[str] = []
        all_issues: list[tuple[str, list[str]]] = []
        omitted_flagged_tests: list[dict[str, object]] = []
        total = 0
        substitutions_total = 0
        metadata_transcodes = 0

        for label in labels:
            relative = safe_path(label, args.scope)
            try:
                actual = no_symlinks(repo, relative)
            except FileNotFoundError:
                if label in required:
                    raise ValueError(f"Required file missing: {label}") from None
                optional_missing.append(label)
                continue

            if actual.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"File exceeds {MAX_FILE_BYTES:,} bytes: {label}")
            raw = actual.read_bytes()
            contents, source_encoding, transcoded = decode_selected_text(raw, relative)
            if args.pseudonymize and relative.suffix.lower() in SOURCE_SUFFIXES:
                transformed, replacements = pseudonymize_copy(contents, label)
            else:
                transformed, replacements = contents, 0
            # Audit only the content that would actually leave the project.
            findings = scan_text(transformed)
            if findings:
                if args.omit_flagged_tests and relative.parts[0] == "tests" and relative.suffix.lower() in SOURCE_SUFFIXES:
                    omitted_flagged_tests.append({
                        "path": relative.as_posix(),
                        "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "finding_count": len(findings),
                        "findings": findings,
                        "reason": "Privacy scanner flagged test fixture; entire file deliberately excluded",
                    })
                    continue
                all_issues.append((label, findings))
            payload = transformed.encode("utf-8") if (replacements or transcoded) else raw
            total += len(payload)
            substitutions_total += replacements
            metadata_transcodes += int(transcoded)
            if total > byte_limit:
                raise ValueError(f"Total exceeds {byte_limit:,} bytes")
            items.append((relative, payload, hashlib.sha256(raw).hexdigest(), replacements,
                          source_encoding, transcoded))

        print(f"{args.scope} selection: {len(items)} files, {total:,} exported bytes")
        print(f"Copy-only pseudonym replacements: {substitutions_total}")
        print(f"BOM-marked UTF-16 metadata converted to UTF-8 copies: {metadata_transcodes}")
        if omitted_flagged_tests:
            print(f"Flagged test files omitted (NOT reviewed or included): {len(omitted_flagged_tests)}")
            for item in omitted_flagged_tests:
                print(f"  {item['path']} ({item['finding_count']} finding(s))")
        if optional_missing:
            print("Optional files not present:")
            for path in optional_missing:
                print(f"  - {path}")
        if all_issues:
            print("\nBLOCKED: review these possible personal details/secrets in the ORIGINAL files:")
            for name, findings in all_issues:
                print(f"  {name}")
                for issue in findings[:30]:
                    print(f"    {issue}")
                if len(findings) > 30:
                    print(f"    ... plus {len(findings) - 30} more findings")
            print("No export created. Do not blindly remove the checks or auto-redact code.")
            return 2

        if args.scan_only:
            print("Scan-only successful. No export created. Human review is still required.")
            return 0

        # All files passed allowlist, size, symlink and heuristic checks BEFORE
        # any export directory is written.
        output.mkdir(parents=True, exist_ok=False)
        manifest = {"profile": args.scope, "files": [], "optional_missing": optional_missing,
                    "deliberately_excluded_export_scripts": export_tool_exclusions,
                    "omitted_flagged_test_files": omitted_flagged_tests,
                    "pseudonymize_name": args.pseudonymize,
                    "pseudonym": PSEUDONYM if args.pseudonymize else None,
                    "note": "Heuristic scan only. No claim of complete anonymisation."}
        for relative, raw, original_sha256, replacements, source_encoding, transcoded in items:
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            manifest["files"].append({
                "path": relative.as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_sha256": original_sha256,
                "pseudonym_replacements": replacements,
                "source_encoding": source_encoding,
                "export_encoding": "utf-8" if transcoded or replacements else source_encoding,
                "metadata_transcoded": transcoded,
            })
        (output / "EXPORT_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (output / "REVIEW_BEFORE_SHARING.md").write_text(
            f"# Mairon {args.scope} — human review required\n\n"
            "This folder contains *individual reviewed-code candidates*, "
            "not the full Mairon repository. The codebase profile includes Python "
            "sources/tests/scripts plus selected root dependency/build metadata, "
            "not documentation, assets, benchmarks or non-Python fixture files. "
            "If --omit-flagged-tests was used, flagged test files are listed in "
            "EXPORT_MANIFEST.json and were deliberately left OUT, not sanitised. "
            "No private databases, account configuration, .env or Git data "
            "were intentionally exported.\n\n"
            "BOM-marked UTF-16 root metadata, when present, is decoded and exported "
            "as UTF-8; the original stays unchanged. Check source/export hashes "
            "and per-file encoding fields in the manifest.\n\n"
            "**Before sharing with Codex:**\n"
            "1. Open every exported file and search for real names, emails, "
            "addresses, schedules, service identifiers, tokens and hardcoded personal details.\n"
            "2. Review EVERY substituted prompt, test expectation, regex and string literal "
            "for semantics (pseudonymized copies are not necessarily functionally equivalent). "
            "Check the manifest for per-file substitution counts and original/export hashes.\n"
            "3. Review test fixtures and other string literals. Automatic scanning "
            "is incomplete. Do not assume passing means sanitised.\n"
            "4. Keep this workspace out of the original repository; use a "
            "genuinely isolated Codex environment if it can run shell commands.\n"
            "5. Provide the reviewed Phase 12.4 blueprint separately; do not "
            "include private chat histories, accounts, backups or credentials.\n"
            "6. Ask Codex for individual modified files/patches and an exact "
            "change manifest, not a ZIP or automatic direct-repository writes. "
            "**Never overwrite real files with pseudonymised exports:** compare "
            "original-versus-export hashes, transfer only intended code edits, "
            "and verify pseudonyms/secrets are not inserted in production. "
            "Integrate, regression-test, commit and push only in the original "
            "repository under local user control.\n\n"
            "**This script does not grant OS-level isolation**: a local Codex "
            "agent with your Windows user's filesystem permissions may still "
            "be able to access the original Mairon directory. Use a sandbox, "
            "separate restricted account/VM, or remote file-only workspace.\n",
            encoding="utf-8"
        )
        print(f"Export created: {output}")
        if omitted_flagged_tests:
            print("IMPORTANT: omitted test files are NOT available to Codex. Run full relevant tests locally on integration.")
        print("IMPORTANT: manual privacy review and actual Codex filesystem isolation are still required.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
