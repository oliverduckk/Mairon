from pathlib import Path
import sys
import types

# Lightweight stubs for focused pure-helper testing.
_ac = types.ModuleType('core.answer_contract_runtime')
def _coerce_contract(value):
    if value is None:
        return None
    text = str(value or '')
    intent = ''
    mode = ''
    for line in text.splitlines():
        if line.lower().startswith('intent:'):
            intent = line.split(':', 1)[1].strip()
        elif line.lower().startswith('epistemic mode:'):
            mode = line.split(':', 1)[1].strip()
    return types.SimpleNamespace(
        intent=intent,
        epistemic_mode=mode,
        allow_new_factual_claims=True,
        metadata={},
    )
_ac.coerce_answer_contract_runtime = _coerce_contract
_ac.render_answer_contract = lambda value: str(value or '')
sys.modules.setdefault('core.answer_contract_runtime', _ac)

_sl = types.ModuleType('core.source_lock')
_sl.build_draft_source_lock_diagnostics = lambda *args, **kwargs: {}
_sl.build_source_lock_instruction = lambda *args, **kwargs: ''
_sl.find_structural_source_lock_violations = lambda *args, **kwargs: []
_sl.recommended_source_lock_prior_window = lambda *args, **kwargs: 4
sys.modules.setdefault('core.source_lock', _sl)

ROOT = Path(__file__).resolve().parents[0]
repo_src = Path(__file__).resolve().parents[1] / 'src'
SRC = repo_src if repo_src.exists() else ROOT
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    _unsupported_relationship_history_claims,
    build_recommendation_request_fallback,
    find_factual_personal_observation_violations,
    find_self_evaluation_overreach_violations,
    find_recommendation_completion_violations,
    find_user_diagnostic_overclaim_violations,
)
from research.public_factual_grounding import build_supported_current_lookup_fallback


def _contract(intent='factual_question', mode='stable_model_knowledge'):
    return (
        f'Intent: {intent}\n'
        f'Epistemic mode: {mode}\n'
        'Authority: local_model_knowledge\n'
    )


def run():
    # B34: exact public evidence that uniquely identifies an episode should be
    # returned extractively rather than letting Qwen invent a negative release
    # claim around the correct number.
    packet = {
        'sources': [{
            'title': '[September 9] Re:Zero – Starting Life in Another World Season 4 Episode 16 “Subaru Natsuki” Preview',
            'search_snippet': 'Season 4 Episode 16 preview published September 9.',
            'content_excerpt': '',
        }]
    }
    exact = build_supported_current_lookup_fallback(
        packet,
        'what was that Natsuki Subaru episode from September 9 everyone was talking about?',
    )
    assert exact == 'The source-supported match for September 9 is Season 4, Episode 16.', exact

    # The recommendation validator must reject a mood-description that never
    # names the thing being recommended; bounded fallback must name a candidate.
    rec_user = 'what should i watch then?'
    rec_contract = _contract('recommendation_request', 'conversation')
    vague = (
        "It’s less comedy and more existential crisis. The characters are trying "
        "to survive while everything else burns."
    )
    rec_bad = find_recommendation_completion_violations(rec_user, vague, rec_contract)
    assert rec_bad, rec_bad
    rec_fallback = build_recommendation_request_fallback(
        rec_user,
        conversation=[
            {'role': 'user', 'content': 'i want something dark and character driven tonight. definitely not a comedy'},
        ],
    )
    assert 'Monster' in rec_fallback, rec_fallback

    # Development self-evaluation may use explicitly supplied context, but it
    # must not invent a long-standing relationship/history like "since day one".
    history_bad = _unsupported_relationship_history_claims(
        draft="Useful? I've been processing your nonsense since day one.",
        grounding_text='we finally added developer diagnostics so i can see routing and model metadata',
    )
    assert history_bad, history_bad
    history_good = _unsupported_relationship_history_claims(
        draft='The diagnostics give you visibility into my routing and model metadata.',
        grounding_text='we finally added developer diagnostics so i can see routing and model metadata',
    )
    assert not history_good, history_good

    self_eval_user = "reckon you're finally becoming useful?"
    self_eval_bad = (
        "Useful? The only thing I've become is more aware of exactly how much "
        "time you waste on trivial things and your questionable decisions."
    )
    assert find_self_evaluation_overreach_violations(self_eval_user, self_eval_bad)
    self_eval_good = (
        'Yeah. The diagnostics you just added give you visibility into my routing and model metadata.'
    )
    assert not find_self_evaluation_overreach_violations(self_eval_user, self_eval_good)

    # Dark-scene VRR follow-ups must not invent local-dimming hardware or claim
    # that a slower/darker scene itself tells VRR to change refresh rate.
    vrr_user = 'could it still be VRR if the flicker only happens in dark scenes? or am i guessing'
    vrr_bad = (
        'Yes. Some panels use local dimming zones, and the panel switches refresh '
        'rates to match a slower scene, which can make the zones flicker.'
    )
    vrr_violations = find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_bad,
        _contract(),
        conversation=[],
    )
    assert any('panel/dimming' in item or 'scene content' in item for item in vrr_violations), vrr_violations

    vrr_good = (
        'Yes, it could still be VRR. Dark scenes can make luminance instability '
        'easier to notice, but that correlation does not prove VRR is the root cause.'
    )
    assert not find_user_diagnostic_overclaim_violations(
        vrr_user,
        vrr_good,
        _contract(),
        conversation=[],
    )

    # Stable factual answers cannot decorate themselves with invented repeated
    # observations of Oliver's personal habits.
    camera_user = 'random tangent: why do mirrorless cameras eat batteries so fast lol'
    camera_bad = (
        "Mirrorless cameras keep displays and processors powered. And don't think "
        "I haven't noticed how often you're hunting for spare batteries in your bag."
    )
    habit_bad = find_factual_personal_observation_violations(
        camera_user,
        camera_bad,
        _contract(),
    )
    assert habit_bad, habit_bad
    camera_good = 'Mirrorless cameras keep the display, sensor and processor active much of the time.'
    assert not find_factual_personal_observation_violations(
        camera_user,
        camera_good,
        _contract(),
    )

    # Wiring checks: salvage must re-run recommendation completion, and exact
    # episode resolution must be allowed to return before model generation.
    provider_path = repo_src / 'ai' / 'ollama_provider.py' if repo_src.exists() else ROOT / 'ollama_provider.py'
    provider_text = provider_path.read_text(encoding='utf-8')
    salvage_start = provider_text.index('salvage_violations = list(')
    salvage_end = provider_text.index('salvage_violations = list(dict.fromkeys', salvage_start)
    salvage_block = provider_text[salvage_start:salvage_end]
    assert 'find_recommendation_completion_violations' in salvage_block
    assert 'Accepted evidence uniquely resolved the requested ' in provider_text
    assert 'media identity; Core returned an extractive answer without model generation.' in provider_text
    assert 'find_factual_personal_observation_violations' in provider_text

    print('Phase 11.6.6B34 final human gate closure: PASS')


if __name__ == '__main__':
    run()
