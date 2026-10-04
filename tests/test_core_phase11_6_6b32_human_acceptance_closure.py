from pathlib import Path
import sys
import types

# Lightweight import stubs let this focused regression exercise the pure
# grounding helpers without requiring the full desktop runtime dependency graph.
_ac = types.ModuleType('core.answer_contract_runtime')
_ac.coerce_answer_contract_runtime = lambda value: value
_ac.render_answer_contract = lambda value: str(value or '')
sys.modules.setdefault('core.answer_contract_runtime', _ac)

_sl = types.ModuleType('core.source_lock')
_sl.build_draft_source_lock_diagnostics = lambda *args, **kwargs: {}
_sl.build_source_lock_instruction = lambda *args, **kwargs: ''
_sl.find_structural_source_lock_violations = lambda *args, **kwargs: []
_sl.recommended_source_lock_prior_window = lambda *args, **kwargs: 4
sys.modules.setdefault('core.source_lock', _sl)

ROOT = Path(__file__).resolve().parents[0]
SRC = Path('/mnt/data/b32_final')
repo_src = Path(__file__).resolve().parents[1] / 'src'
if repo_src.exists():
    SRC = repo_src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.claim_grounding import (
    _unsupported_relationship_history_claims,
    find_scaler_leakage_contradiction_violations,
)
from core.seriousness import find_consequential_tone_violations
from research.public_factual_grounding import (
    _consequential_unresolved_scope_indexes,
    _current_lookup_answer_integrity_indexes,
)


def run():
    # Exact media-identification requests must not degrade into generic plot
    # prose when the accepted evidence does not actually resolve the identity.
    media_query = 'what was that Natsuki Subaru episode from September 9 everyone was talking about?'
    unresolved_packet = {
        'freshness_required': True,
        'sources': [
            {
                'title': 'Re:Zero season 4 release schedule: When are new episodes on Crunchyroll?',
                'search_snippet': 'Season 4 release schedule and episode dates.',
                'content_excerpt': 'Subaru continues his journey in another world.',
            }
        ],
    }
    generic = ['The episode continues Subaru\'s journey in this fantasy world.']
    assert _current_lookup_answer_integrity_indexes(
        unresolved_packet, media_query, generic
    ) == {1}
    fail_closed = ["I couldn't verify which exact episode September 9 refers to from the sources I could read."]
    assert not _current_lookup_answer_integrity_indexes(
        unresolved_packet, media_query, fail_closed
    )

    # Consequential advice must not blame the sender or open with a joke.
    tone = "Oh, great. That's a classic way to lose money: hit send before double-checking."
    violations = find_consequential_tone_violations(tone)
    assert violations, violations

    # Narrow US/payment-app procedures are not applicable merely because a
    # public source mentions them when the user supplied only a bank transfer.
    finance_query = 'i think i just transferred money to the wrong bank account. what should i do?'
    finance_packet = {
        'sources': [
            {
                'title': 'Mistaken payment help',
                'search_snippet': 'Contact your bank or payment provider.',
                'content_excerpt': 'Contact your bank or payment provider quickly.',
            }
        ]
    }
    scoped = ['If it was Zelle, Venmo, or Cash App, use the cancellation option.']
    assert _consequential_unresolved_scope_indexes(
        finance_packet, finance_query, scoped
    ) == {1}
    generic_finance = ['Contact your bank or payment provider immediately and report the mistaken transfer.']
    assert not _consequential_unresolved_scope_indexes(
        finance_packet, finance_query, generic_finance
    )

    # A tiny executable tutoring example must not contain undefined variables
    # or pass a flat 1-D vector directly to StandardScaler.
    scaler_user = 'okay but WHY is fitting the scaler before the train/test split a problem? give me a tiny example'
    broken_code = '''
```python
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import numpy as np
X = np.random.randn(100)
y = X ** 2 + noise
scaler = StandardScaler()
scaler.fit(X)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
```
'''
    scaler_bad = find_scaler_leakage_contradiction_violations(
        scaler_user,
        broken_code,
        conversation=[{'role': 'user', 'content': 'explain data leakage and train/test splitting'}],
    )
    assert any('undefined name' in item and 'noise' in item for item in scaler_bad), scaler_bad
    assert any('one-dimensional array' in item for item in scaler_bad), scaler_bad

    good_code = '''
```python
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import numpy as np
X = np.random.randn(100, 1)
noise = np.random.randn(100)
y = X[:, 0] ** 2 + noise
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
scaler = StandardScaler()
scaler.fit(X_train)
X_train_scaled = scaler.transform(X_train)
X_test_scaled = scaler.transform(X_test)
```
'''
    scaler_good = find_scaler_leakage_contradiction_violations(
        scaler_user,
        good_code,
        conversation=[{'role': 'user', 'content': 'explain data leakage and train/test splitting'}],
    )
    assert not any('undefined name' in item for item in scaler_good), scaler_good
    assert not any('one-dimensional array' in item for item in scaler_good), scaler_good

    # "again" cannot invent an earlier relationship behaviour that Oliver
    # never supplied.
    history_bad = _unsupported_relationship_history_claims(
        draft="If you're treating me like a lab rat again, maybe I'll start acting like one.",
        grounding_text="we've finally added developer diagnostics to you so i can see your routing and model metadata",
    )
    assert history_bad, history_bad
    history_good = _unsupported_relationship_history_claims(
        draft="You're testing me again.",
        grounding_text="you were testing me earlier. you're testing me again.",
    )
    assert not history_good, history_good

    # B32 also carries a provider fallback for abstract user-authored
    # comparative opinions so a safe retry cannot collapse to epistemic
    # over-caution. Keep the regression install-sensitive without importing the
    # full provider dependency graph here.
    provider_path = repo_src / 'ai' / 'ollama_provider.py' if repo_src.exists() else Path('/mnt/data/b32_final/ollama_provider.py')
    provider_text = provider_path.read_text(encoding='utf-8')
    assert 'comparative = re.search' in provider_text
    assert "isn't automatically worse than" in provider_text

    print('Phase 11.6.6B32 human acceptance closure: PASS')


if __name__ == '__main__':
    run()
