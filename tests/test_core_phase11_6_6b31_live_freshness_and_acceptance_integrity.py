from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[0]
SRC = Path('/mnt/data/b31_work/src')
repo_src = Path(__file__).resolve().parents[1] / 'src'
if repo_src.exists():
    SRC = repo_src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_tool_registry_stub = types.ModuleType('tools.tool_registry')
_tool_registry_stub.execute_tool = lambda *args, **kwargs: None
sys.modules.setdefault('tools.tool_registry', _tool_registry_stub)

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from core.seriousness import find_consequential_tone_violations
from research import public_factual_research as pfr
from research.public_factual_grounding import (
    _consequential_specific_procedure_indexes,
    _current_lookup_answer_integrity_indexes,
    _live_lookup_capability_contradiction_indexes,
)


def run():
    query = 'what is the latest version of minecraft java?'

    # Current-version retrieval must bias toward recent release pages rather
    # than accepting an old version page just because it contains a version.
    calls = []

    def fake_execute_tool(name, payload):
        calls.append((name, dict(payload)))
        if name == 'web_search':
            return {
                'success': True,
                'results': [
                    {
                        'title': 'Minecraft Java Edition 1.21 release guide',
                        'url': 'https://example.org/minecraft-java-1-21',
                        'content': 'Minecraft Java Edition 1.21 was released in 2024.',
                        'published_date': '2024-06-01',
                        'score': 0.99,
                    },
                    {
                        'title': 'Minecraft Java Edition 26.3 | Minecraft',
                        'url': 'https://www.minecraft.net/en-us/article/minecraft-java-edition-26-3',
                        'content': 'Minecraft Java 26.3 Released',
                        'published_date': '2026-09-15',
                        'score': 0.90,
                    },
                ],
            }
        if name == 'web_read':
            if '26-3' in payload.get('url', ''):
                return {
                    'success': True,
                    'content': 'Minecraft Java Edition 26.3. Minecraft Java 26.3 Released. Latest Release.',
                }
            return {
                'success': True,
                'content': 'Minecraft Java Edition 1.21 was released in 2024.',
            }
        raise AssertionError(name)

    original_execute_tool = pfr.execute_tool
    pfr.execute_tool = fake_execute_tool
    try:
        result = pfr.gather_public_factual_research(
            user_input=query,
            max_reads=1,
            require_query_resolution=True,
            require_quality_evidence=True,
        )
    finally:
        pfr.execute_tool = original_execute_tool

    assert result['success'] is True, result
    assert result['time_range'] == 'year', result
    assert 'official release notes' in result['search_query'].lower(), result
    accepted = [
        source for source in result['sources']
        if source.get('accepted_as_evidence') is not False and source.get('read_success')
    ]
    assert accepted, result
    assert '26.3' in (accepted[0].get('title') or ''), accepted
    assert calls[0][1]['time_range'] == 'year', calls

    stale_source = {
        'title': 'Minecraft Java Edition 1.21 release',
        'url': 'https://example.org/minecraft-java-1-21',
        'source_host': 'example.org',
        'snippet': 'Minecraft Java Edition 1.21 released.',
        'published_date': '2024-06-01',
        'read_success': True,
        'read_result': {'success': True, 'content': 'Minecraft Java Edition 1.21 release notes.'},
    }
    rel = pfr.assess_public_source_relevance(
        stale_source,
        query=query,
        research_identity=query,
        include_read_content=True,
    )
    assert rel['accepted'] is False, rel

    packet = {
        'freshness_required': True,
        'sources': [
            {
                'title': 'Minecraft Java Edition 26.3 | Minecraft',
                'search_snippet': 'Minecraft Java 26.3 Released',
                'content_excerpt': 'Minecraft Java Edition 26.3. Latest Release.',
                'published_date': '2026-09-15',
            }
        ],
    }

    denial = ["As of my last update, I don't have access to real-time data, so check Mojang's website."]
    assert _live_lookup_capability_contradiction_indexes(packet, query, denial) == {1}
    assert _current_lookup_answer_integrity_indexes(packet, query, denial) == {1}

    good_current = ['Minecraft Java Edition 26.3 is the current release in the evidence I checked.']
    assert not _live_lookup_capability_contradiction_indexes(packet, query, good_current)
    assert not _current_lookup_answer_integrity_indexes(packet, query, good_current)

    media_packet = {
        'freshness_required': True,
        'sources': [
            {
                'title': '[September 9] Re:Zero Season 4 Episode 16 “Subaru Natsuki” Preview',
                'search_snippet': 'Preview for Episode 16 on September 9.',
                'content_excerpt': 'Episode 16 preview information.',
            }
        ],
    }
    media_query = 'what was that Natsuki Subaru episode from September 9 everyone was talking about?'
    assert _current_lookup_answer_integrity_indexes(
        media_packet,
        media_query,
        ['The episode aired on September 9, 2026.'],
    ) == {1}

    finance_packet = {
        'sources': [
            {
                'title': 'Mistaken payment help',
                'search_snippet': 'Contact the transfer provider immediately.',
                'content_excerpt': 'Contact the provider and report the mistaken transfer.',
            }
        ],
    }
    finance_query = 'i think i just transferred money to the wrong bank account. what should i do?'
    assert _consequential_specific_procedure_indexes(
        finance_packet,
        finance_query,
        ['File a chargeback and contact the fraud team.'],
    ) == {1}

    # StandardScaler uses population std (ddof=0), so these sample-std values
    # are internally wrong for the displayed numbers.
    scaler_user = 'okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example'
    scaler_bad = '''
Train: [[1], [2]]
Test: [[3], [4]]
Fit on Train only: mean = 1.5, std = 0.707.
Fit on the whole dataset: mean = 2.5, std = 1.29.
'''
    scaler_violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        conversation=[{'role': 'user', 'content': 'explain data leakage and train/test splitting'}],
    )
    assert any('standard deviation inconsistent' in item for item in scaler_violations), scaler_violations

    wifi_contract = AnswerContractRuntime(
        intent='factual_question',
        epistemic_mode='stable_model_knowledge',
    )
    wifi_user = "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. bruh don't tell me to buy a new router straight away, what would you test first?"
    wifi_bad = "600 Mbps on the console and 20 on the phone? That's a classic Wi-Fi range issue, not a router failure."
    wifi_violations = find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_bad,
        wifi_contract,
        conversation=[],
    )
    assert any('single unmeasured Wi-Fi root cause' in item for item in wifi_violations), wifi_violations

    tone_bad = "Right, I assume you're not about to freeze up or stare at a screen like something's broken."
    tone_violations = find_consequential_tone_violations(tone_bad)
    assert tone_violations, tone_violations

    print('Phase 11.6.6B31 live freshness and acceptance integrity: PASS')


if __name__ == '__main__':
    run()
