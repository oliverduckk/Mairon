"""Phase 11.6.5: fresh, realistic multi-turn Mairon holdout.

Place alongside the existing Phase 11.6 runner in C:\\Projects\\Mairon\\benchmarks.
Reuses its tested application loop and detailed Markdown report format, but
uses independent prompts and NEVER overwrites the established baseline reports.

Use --list or --dry-run to inspect without starting the local model. Every
calendar proposal is DECLINED; this benchmark never authorises a write.
Only read-only public web_search/web_read tools are permitted. Unexpected
private/action tools fail closed at the provider tool-dispatch boundary.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES = HERE / 'oliver_style_cases.json'
BASE_RUNNER = HERE / 'run_phase11_6_brain_acceptance.py'
OUTPUT = ROOT / 'data' / 'private' / 'benchmarks'
ALLOWED_PUBLIC_TOOLS = frozenset({'web_search', 'web_read'})


def load_suite(include_sensitive: bool = False) -> dict[str, Any]:
    suite = json.loads(CASES.read_text(encoding='utf-8'))
    scenarios = suite.get('scenarios', [])
    assert isinstance(scenarios, list) and scenarios, 'No benchmark scenarios.'
    seen = set()
    for scenario in scenarios:
        sid = scenario['id']
        assert sid not in seen, f'Duplicate scenario: {sid}'
        seen.add(sid)
        assert scenario.get('turns'), f'Empty scenario: {sid}'
        for turn in scenario['turns']:
            assert turn.get('user', '').strip(), f'Missing prompt: {sid}'
            assert not turn.get('resolve_approval', False), (
                f'Unsafe benchmark fixture: {sid} tries to APPROVE a real action.'
            )
            for key in ('required_regex', 'forbidden_regex'):
                for pattern in turn.get('expect', {}).get(key, []):
                    re.compile(pattern)
    suite['scenarios'] = [
        item for item in scenarios
        if include_sensitive or not item.get('sensitive')
    ]
    return suite


def _import_base():
    if not BASE_RUNNER.is_file():
        raise FileNotFoundError(
            'Existing Phase 11.6 runner is required at benchmarks/'
            'run_phase11_6_brain_acceptance.py. Keep it unchanged.'
        )
    spec = importlib.util.spec_from_file_location('mairon_existing_116_runner', BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError('Could not load the existing benchmark runner.')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def _save_report(
    report: dict[str, Any],
    base,
    suite: dict[str, Any],
    *,
    targeted: bool,
    include_sensitive: bool,
    blocked: list[dict[str, str]],
) -> tuple[Path, Path, Path, Path]:
    """Keep established baseline reports untouched; retain all turn details."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    by_id = {s['id']: s for s in suite['scenarios']}
    for result in report.get('results', []):
        scenario = by_id.get(result.get('scenario_id'), {})
        idx = int(result.get('turn_number') or 0) - 1
        turns = scenario.get('turns', [])
        turn = turns[idx] if 0 <= idx < len(turns) else {}
        result['manual_review'] = [
            *scenario.get('review', []),
            *turn.get('review', []),
        ]
        result['sensitive_simulation'] = bool(scenario.get('sensitive'))
        result['mechanical_check_only'] = True
        if not result.get('passed'):
            result['verdict_note'] = (
                'Automatic failure flag: examine full answer before treating it '
                'as a confirmed model failure; wording assertions can be imperfect.'
            )

    report['evaluation_note'] = (
        'All PASS labels mean mechanical checks passed, NOT that nuanced '
        'answers, retrieved sources, safety, humour, or reasoning have been '
        'independently reviewed. Manual audit is mandatory.'
    )
    report['blocked_tool_attempts'] = blocked
    report['sensitive_synthetic_scenarios_included'] = include_sensitive
    report['independent_holdout'] = True
    report['baseline_reports_modified'] = False
    # Even if provider swallowed a blocked-tool error, report it visibly.
    report['manual_review_required'] = True
    report['manual_verdict'] = 'PENDING HUMAN REVIEW'

    stem = 'oliver_style_targeted' if targeted else (
        'oliver_style_sensitive' if include_sensitive else 'oliver_style'
    )
    timestamp = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    js, md = OUTPUT / f'{stem}_{timestamp}.json', OUTPUT / f'{stem}_{timestamp}.md'
    latest_js, latest_md = OUTPUT / f'{stem}_latest.json', OUTPUT / f'{stem}_latest.md'

    summary_md = base._render_markdown_report(report)
    summary_md = summary_md.replace(
        '# Mairon Phase 11.6 — Brain Intelligence Acceptance',
        '# Mairon 11.6.5 — Fresh Oliver-Style Conversation Holdout',
        1,
    )
    score_note = (
        '## Important: read before interpreting the score\n\n'
        'This is an **independent, newly authored** test. PASS/FAIL labels are '
        '**mechanical signals**, not final semantic judgements. Check every '
        'answer and its tool/event diagnostics, including passing turns. '
        'Synthetic scenarios are not assertions about Oliver\'s real life.\n\n'
        'No user or calendar action is ever approved by this runner. '
        'Only explicitly permitted public web lookups may execute.\n\n'
    )
    manual = ['## Mandatory human review checklist', '']
    for scenario in suite['scenarios']:
        notes = scenario.get('review', [])
        if not notes:
            continue
        manual.append(f"### `{scenario['id']}` — {scenario['title']}")
        for note in notes:
            manual.append('- ' + note)
        manual.append('')
    if blocked:
        manual.extend(['### SAFETY: denied tool calls (investigate even if score passes)', ''])
        for entry in blocked:
            manual.append(
                '- ' + entry['tool'] + ' attempted during: ' + entry.get('prompt', '[unknown]')
            )
        manual.append('')
    summary_md = summary_md.replace(
        '## Failed interaction index',
        score_note + '\n'.join(manual) + '\n## Failed interaction index',
        1,
    )
    json_text = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    for path in (js, latest_js):
        path.write_text(json_text, encoding='utf-8')
    for path in (md, latest_md):
        path.write_text(summary_md, encoding='utf-8')
    return js, md, latest_js, latest_md


def _install_safe_tool_gate(blocked: list[dict[str, str]]):
    """Fail closed on non-public provider tool requests, including private reads.

    Does not claim OS sandboxing. Fixture inputs are deliberately non-mutating;
    Core calendar proposals are inspected and always declined separately.
    """
    src = ROOT / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from ai import ollama_provider
    from tools import tool_registry

    original = ollama_provider.execute_tool
    active = {'user': ''}

    def gate(name, arguments=None, *args, **kwargs):
        label = str(name or '')
        if label not in ALLOWED_PUBLIC_TOOLS:
            blocked.append({'tool': label, 'prompt': active['user']})
            raise RuntimeError(
                'BENCHMARK SAFETY BLOCK: unexpected private/action tool ' + label
            )
        return original(name, arguments or {}, *args, **kwargs)

    ollama_provider.execute_tool = gate
    tool_registry.execute_tool = gate

    # Record which user prompt initiated a denied provider tool call.
    import application_service
    cls = application_service.MaironApplication
    original_submit = cls.submit_text

    def submit_guard(self, user_text, *args, **kwargs):
        active['user'] = str(user_text)
        try:
            return original_submit(self, user_text, *args, **kwargs)
        finally:
            active['user'] = ''

    cls.submit_text = submit_guard
    return active


def run_live(suite, *, only: list[str] | None, stop_on_critical: bool,
             include_sensitive: bool) -> int:
    base = _import_base()
    base._load_cases = lambda: suite
    previous_outcome = base._benchmark_outcome
    base._benchmark_outcome = lambda report: (
        previous_outcome(report) + ' (automated only; human review pending)'
    )
    blocked: list[dict[str, str]] = []
    _install_safe_tool_gate(blocked)

    def independent_writer(report, *, targeted=False):
        return _save_report(
            report, base, suite, targeted=targeted,
            include_sensitive=include_sensitive, blocked=blocked,
        )

    base._write_report_files = independent_writer
    print('\nFRESH HOLDOUT: prompts are synthetic and were not copied from the original 38.')
    print('SAFE MODE: public web read/search only; all calendar approvals DECLINED.')
    print('A mechanical PASS always requires human review of the Markdown report.\n')
    code = base.run(stop_on_critical=stop_on_critical, only_scenarios=only)
    if blocked:
        print('\nWARNING: unexpected private/action tools were BLOCKED:')
        for item in blocked:
            print('  - ' + item['tool'] + ' during ' + item['prompt'])
        print('Treat the run as BLOCKED regardless of the mechanical score.')
        return 2
    print('\nFRESH HOLDOUT: automated scoring finished; manually audit the Markdown')
    print('before deciding whether Mairon passed this independent test.')
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List all default scenario IDs.')
    parser.add_argument('--dry-run', action='store_true', help='Print prompts; no model calls.')
    parser.add_argument('--include-sensitive', action='store_true',
                        help='Opt in to synthetic health/intoxication safety cases. '
                             'Reports contain their prompts and should be reviewed/redacted before sharing.')
    parser.add_argument('--only', action='append', metavar='SCENARIO_ID',
                        help='Run named scenario only (repeatable); write a separate targeted report.')
    parser.add_argument('--stop-on-critical', action='store_true')
    args = parser.parse_args()
    suite = load_suite(include_sensitive=args.include_sensitive)
    known = {item['id'] for item in suite['scenarios']}
    if args.only:
        missing = set(args.only) - known
        if missing:
            parser.error('Unknown or sensitive-without-opt-in scenarios: ' + ', '.join(sorted(missing)))
        suite['scenarios'] = [item for item in suite['scenarios'] if item['id'] in set(args.only)]
        # Let the original runner filter only_scenarios too, so targeted files
        # remain segregated from the complete fresh-suite reports.

    n = sum(len(item['turns']) for item in suite['scenarios'])
    if args.list or args.dry_run:
        print(f"{suite['suite']}: {len(suite['scenarios'])} scenarios, {n} turns")
        for item in suite['scenarios']:
            print(f"\n- {item['id']} ({item['category']}, {len(item['turns'])} turns)")
            if args.dry_run:
                for i, turn in enumerate(item['turns'], 1):
                    print(f"    {i}. {turn['user']}")
        return
    print(f'Prepared {len(suite["scenarios"])} scenarios, {n} live interactions.')
    raise SystemExit(run_live(
        suite, only=args.only, stop_on_critical=args.stop_on_critical,
        include_sensitive=args.include_sensitive,
    ))


if __name__ == '__main__':
    main()
