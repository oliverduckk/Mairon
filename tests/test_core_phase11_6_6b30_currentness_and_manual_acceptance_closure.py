from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[0]
SRC = Path('/mnt/data/mairon_work/src')
# When installed in Mairon/tests, use repository src instead.
repo_src = Path(__file__).resolve().parents[1] / 'src'
if repo_src.exists():
    SRC = repo_src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.epistemic_router import classify_factual_authority
from core.claim_grounding import (
    _unsupported_user_physical_action_claims,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from research.public_factual_grounding import (
    _media_identity_support_indexes,
    _cross_source_temporal_join_indexes,
    find_grounded_opinion_response_violations,
)

_tool_registry_stub = types.ModuleType('tools.tool_registry')
_tool_registry_stub.execute_tool = lambda *args, **kwargs: None
sys.modules.setdefault('tools.tool_registry', _tool_registry_stub)

# Import after stubbing optional tool registry.
from research.public_factual_research import assess_public_source_relevance


def run():
    # Explicit latest/current software versions are live public state.
    query = 'what is the latest version of minecraft java?'
    assert classify_factual_authority(query) == 'public_source_verified'

    bad_version_source = {
        'title': 'Minecraft Java tips and tricks',
        'url': 'https://example.org/minecraft-java-guide',
        'source_host': 'example.org',
        'snippet': 'A guide to Minecraft Java Edition gameplay.',
        'read_success': True,
        'read_result': {'success': True, 'content': 'Minecraft Java Edition guide and tutorial.'},
    }
    rel = assess_public_source_relevance(
        bad_version_source,
        query=query,
        research_identity=query,
        include_read_content=True,
    )
    assert rel['accepted'] is False, rel
    assert any('current software version' in reason for reason in rel['reasons']), rel

    good_version_source = {
        'title': 'Minecraft Java Edition 1.21.10 release',
        'url': 'https://example.org/minecraft-java-1-21-10',
        'source_host': 'example.org',
        'snippet': 'Minecraft Java Edition 1.21.10 is the latest stable release.',
        'read_success': True,
        'read_result': {'success': True, 'content': 'Release notes for Minecraft Java Edition 1.21.10.'},
    }
    rel = assess_public_source_relevance(
        good_version_source,
        query=query,
        research_identity=query,
        include_read_content=True,
    )
    assert rel['accepted'] is True, rel

    # A nearby NVIDIA feature story is not enough to establish a current driver release.
    bad_driver = {
        'title': 'NVIDIA RTX Gets Shader Delivery After AMD Performance Cut',
        'url': 'https://example.org/nvidia-shader-delivery',
        'source_host': 'example.org',
        'snippet': 'The feature works with recent NVIDIA software and drivers.',
        'read_success': True,
        'read_result': {'success': True, 'content': 'The article later mentions a driver version in passing.'},
    }
    rel = assess_public_source_relevance(
        bad_driver,
        query='is there a new NVIDIA driver out right now',
        research_identity='is there a new NVIDIA driver out right now',
        include_read_content=True,
    )
    assert rel['accepted'] is False, rel

    # Exact episode identity must come from source-facing metadata, not a different
    # number buried inside a long schedule page.
    packet = {
        'sources': [
            {
                'title': '[September 9] Re:Zero Season 4 Episode 16 “Subaru Natsuki” Preview',
                'search_snippet': 'Preview published for September 9.',
                'content_excerpt': 'Season 4 episode details and preview information.',
            },
            {
                'title': 'Re:Zero season 4 release schedule',
                'search_snippet': 'When new episodes arrive.',
                'content_excerpt': 'A long weekly release schedule.',
            },
        ]
    }
    flagged = _media_identity_support_indexes(
        packet,
        'what was that Natsuki Subaru episode from September 9 everyone was talking about?',
        ['That was Re:Zero Season 4, Episode 5.', 'The episode covers part of the Loss Arc.'],
    )
    assert 1 in flagged, flagged
    assert 2 in flagged, flagged

    # Facts from separate events/sources may not be stitched into one timeline.
    join_packet = {
        'sources': [
            {
                'title': 'Class poll involving Yamauchi',
                'search_snippet': 'Yamauchi conspiracy was revealed before the class vote.',
                'content_excerpt': 'The class discussed Yamauchi and the conspiracy before the poll.',
            },
            {
                'title': 'Horikita expulsion vote',
                'search_snippet': 'Horikita volunteered for expulsion during another vote.',
                'content_excerpt': 'She volunteered herself for expulsion in that separate exam.',
            },
        ]
    }
    flagged = _cross_source_temporal_join_indexes(
        join_packet,
        ["She volunteered for expulsion and then revealed Yamauchi's conspiracy just before the vote."],
    )
    assert flagged == {1}, flagged

    opinion_bad = "If you're pissed off, I'm inclined to agree with you."
    assert find_grounded_opinion_response_violations(
        'do you think she handled it well though?',
        opinion_bad,
    )

    # Bare activation must not invent Oliver staring at a wall.
    scene_bad = "I've been waiting for you to stop staring at the wall."
    assert _unsupported_user_physical_action_claims(
        scene_bad,
        'Mairon.',
    )

    # Near-main-node speed does not rule out upstairs signal loss/coverage.
    wifi_user = 'tested it: phone hits 580 next to the main mesh node, but still 20 upstairs. so what does that rule out?'
    wifi_bad = 'That rules out a simple signal loss issue between the node and the upstairs device.'
    diagnostic_contract = '''
CORE ANSWER CONTRACT:
- Intent: factual_question
- Epistemic mode: user_context_reasoning
'''
    assert find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_bad,
        diagnostic_contract,
        conversation=[{'role': 'user', 'content': 'my wired console is getting 600 Mbps but my phone upstairs barely hits 20. what would you test first?'}],
    )

    # Tiny scaler examples must be internally numerically consistent.
    scaler_user = 'okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example'
    scaler_bad = '''
train = [[1], [2], [3]]
test = [[4], [5]]
If you fit on train + test, the scaler computes mean = 3.5 from all 5 points.
'''
    violations = find_scaler_leakage_contradiction_violations(
        scaler_user,
        scaler_bad,
        conversation=[{'role': 'user', 'content': 'explain data leakage and train/test splitting'}],
    )
    assert any('mean inconsistent' in item for item in violations), violations

    # The bounded opinion fallback must not claim Oliver supplied framing he never supplied.
    provider_source = (SRC / 'ai' / 'ollama_provider.py').read_text(encoding='utf-8')
    fallback_start = provider_source.index('def build_substantive_opinion_fallback')
    fallback_end = provider_source.index('def find_core_micro_act_relevance_violations', fallback_start)
    fallback_block = provider_source[fallback_start:fallback_end]
    assert 'the framing you gave me is defensible' not in fallback_block
    assert "I don't know enough about " in fallback_block

    print('Phase 11.6.6B30 currentness and manual acceptance closure: PASS')


if __name__ == '__main__':
    run()
