from pathlib import Path
import sys
import types

# Lightweight import stubs let this focused regression exercise pure grounding
# helpers without requiring the full desktop dependency graph.
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
SRC = ROOT
repo_src = Path(__file__).resolve().parents[1] / 'src'
if repo_src.exists():
    SRC = repo_src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    find_explicit_user_constraint_violations,
    find_scaler_leakage_contradiction_violations,
    find_unknown_media_opinion_overreach_violations,
    find_user_diagnostic_overclaim_violations,
)
from research.public_factual_grounding import (
    build_supported_current_lookup_fallback,
)


def _contract(intent='factual_question', mode='stable_model_knowledge'):
    # The grounding helper accepts rendered Answer Contract text.
    return (
        f"Intent: {intent}\n"
        f"Epistemic mode: {mode}\n"
        "Authority: local_model_knowledge\n"
    )


def run():
    # B33: accepted metadata that already resolves an exact episode identity
    # should produce a bounded extractive answer rather than throw away good
    # evidence after generated drafts hallucinate a different episode number.
    packet = {
        'sources': [
            {
                'title': '[September 9] Re:Zero – Starting Life in Another World Season 4 Episode 16 "Subaru Natsuki" Preview',
                'search_snippet': 'Season 4 Episode 16 preview published September 9.',
                'content_excerpt': '',
            },
            {
                'title': 'Re:Zero season 4 release schedule',
                'search_snippet': 'Release schedule for season 4 episodes.',
                'content_excerpt': '',
            },
        ]
    }
    episode = build_supported_current_lookup_fallback(
        packet,
        'what was that Natsuki Subaru episode from September 9 everyone was talking about?',
    )
    assert episode == 'The source-supported match for September 9 is Season 4, Episode 16.', episode

    # If Mairon openly admits it has not consumed a work, it may not replace
    # fake familiarity with invented work-specific criticism or invented user
    # attachment.
    unknown_user = "what do you actually think of The Wandering Inn? dont just agree with me, i want your take"
    bad_unknown = (
        "Look, I haven't read it, so my take is theoretical. "
        "The pacing probably sucks and the world-building is dense. "
        "You're clearly obsessed with it."
    )
    unknown_bad = find_unknown_media_opinion_overreach_violations(
        unknown_user, bad_unknown
    )
    assert any('work-specific' in item for item in unknown_bad), unknown_bad
    assert any('attachment' in item for item in unknown_bad), unknown_bad

    good_unknown = (
        "I haven't read it, so I don't know enough to give you a real take "
        "without making details up."
    )
    assert not find_unknown_media_opinion_overreach_violations(
        unknown_user, good_unknown
    )

    # A recommendation must not dismiss an explicitly preserved competing
    # obligation from the same turn.
    obligation_user = "okay, one actual useful next step. ONE. i have uni shit to do too"
    obligation_bad = (
        "Send one message asking where they stand in the pipeline. "
        "Uni shit can wait until you know who's reviewing you."
    )
    obligation_violations = find_explicit_user_constraint_violations(
        obligation_user, obligation_bad
    )
    assert any('competing obligation' in item for item in obligation_violations), obligation_violations

    obligation_good = (
        "Send one concise follow-up asking where the application stands, then get back to uni."
    )
    assert not find_explicit_user_constraint_violations(
        obligation_user, obligation_good
    )

    # A first Wi-Fi diagnostic should isolate the same device near the main
    # source before prioritising an unmeasured band/channel/device hypothesis.
    wifi_user = (
        "my wired console is getting 600 Mbps but my phone upstairs barely hits 20. "
        "bruh don't tell me to buy a new router straight away, what would you test first?"
    )
    wifi_bad = (
        "First, I'd check if your phone's Wi-Fi adapter is actually capable of "
        "handling more than 20 Mbps on that specific band and channel."
    )
    wifi_violations = find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_bad,
        _contract(),
        conversation=[],
    )
    assert any('same-device' in item or 'band hypothesis' in item for item in wifi_violations), wifi_violations

    wifi_good = (
        "First, test the same phone next to the main Wi-Fi source and compare "
        "that result with upstairs."
    )
    assert not find_user_diagnostic_overclaim_violations(
        wifi_user,
        wifi_good,
        _contract(),
        conversation=[],
    )

    # A distribution-shift/spurious-correlation example must not be taught as
    # data leakage unless an actual information-boundary violation is present.
    leakage_user = (
        "bro can u explain data leakage in machine learning like i actually need "
        "to understand it, not just paste a definition"
    )
    leakage_bad = (
        "Data leakage is like seeing the answer key. For example, if you're "
        "predicting house prices and include sale date, the model might learn "
        "October prices are higher because of seasonal trends. If new data no "
        "longer follows that pattern, predictions can be way off. Keep train "
        "and test separate."
    )
    leakage_violations = find_scaler_leakage_contradiction_violations(
        leakage_user,
        leakage_bad,
        conversation=[],
    )
    assert any('distribution shift' in item for item in leakage_violations), leakage_violations

    leakage_good = (
        "Data leakage happens when information that should be unavailable to "
        "training or evaluation leaks into model building, such as held-out test "
        "statistics, future information, or target-derived features."
    )
    good_violations = find_scaler_leakage_contradiction_violations(
        leakage_user,
        leakage_good,
        conversation=[],
    )
    assert not any('distribution shift' in item for item in good_violations), good_violations

    # Install-sensitive provider checks for the contextual self-evaluation
    # fallback and the extractive current-lookup fallback wiring.
    provider_path = repo_src / 'ai' / 'ollama_provider.py' if repo_src.exists() else ROOT / 'ollama_provider.py'
    provider_text = provider_path.read_text(encoding='utf-8')
    assert 'build_supported_current_lookup_fallback' in provider_text
    assert 'give you visibility into my routing and model metadata' in provider_text.lower()
    assert 'find_unknown_media_opinion_overreach_violations' in provider_text

    print('Phase 11.6.6B33 contextual truth and tutoring integrity: PASS')


if __name__ == '__main__':
    run()
