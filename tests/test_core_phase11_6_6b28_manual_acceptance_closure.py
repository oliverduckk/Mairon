from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.answer_contract_runtime import AnswerContractRuntime
from core.claim_grounding import (
    _unsupported_mairon_perception_claims,
    _unsupported_relationship_history_claims,
    find_python_mutable_default_semantics_violations,
    find_scaler_leakage_contradiction_violations,
    find_user_diagnostic_overclaim_violations,
)
from personality.spoiler_guard import find_spoiler_guard_violations
from research.public_factual_grounding import (
    _deterministic_labeled_numeric_relation_indexes,
    build_public_factual_retry_instruction,
)


def run():
    # Hard spoiler ceilings must block future-outcome teasing even when the
    # assistant does not name a character or chapter beyond the boundary.
    spoiler_context = {
        "must_ask_progress": False,
        "must_complete_progress": False,
        "must_confirm_latest": False,
        "profile": {"progress_type": "chapter", "progress_value": 25},
        "current_user_text": "i've only read the first 25 chapters. do NOT spoil shit past that",
        "user_grounding_text": "i've only read the first 25 chapters. do NOT spoil shit past that",
    }
    spoiler_bad = (
        "Noted. I'll keep my mouth shut about anything after chapter 25, "
        "because apparently you're not ready to see your favourite characters get their comeuppance yet."
    )
    violations = find_spoiler_guard_violations(spoiler_bad, spoiler_context)
    assert violations, violations
    assert any("spoiler ceiling" in item for item in violations), violations
    assert not find_spoiler_guard_violations(
        "Noted. I'll keep anything after chapter 25 off-limits.",
        spoiler_context,
    )

    # Mutable defaults are a language semantic, not an optimisation/caching
    # trick to save memory.
    mutable_user = (
        "python question: `def f(x=[]): x.append(7); return x` then "
        "`print(f()); print(f())` -- what prints?"
    )
    bad_mutable = (
        "Python evaluates the default once at definition time and reuses it. "
        "It's just caching the same list object to save memory."
    )
    violations = find_python_mutable_default_semantics_violations(
        user_input=mutable_user,
        draft=bad_mutable,
        conversation=[],
    )
    assert any("caching/memory" in item for item in violations), violations

    # A tiny scaler-leakage example must not contain classifier code that
    # cannot execute because the training slice contains only one class.
    scaler_user = (
        "okay but WHY is fitting the scaler before the train/test split a problem? "
        "give me a tiny example"
    )
    bad_scaler = """
Suppose X = [1,2,3,4,5,6].
```python
X = np.array([[1],[2],[3],[4],[5],[6]])
y = np.array([0,0,0,1,1,1])
scaler = StandardScaler().fit(X)
X_train_scaled = scaler.transform(X[:3])
X_test_scaled = scaler.transform(X[3:])
model = LogisticRegression()
model.fit(X_train_scaled, y[:3])
score = model.score(X_test_scaled, y[3:])  # inflated score!
```
"""
    violations = find_scaler_leakage_contradiction_violations(
        user_input=scaler_user,
        draft=bad_scaler,
        conversation=[
            {
                "role": "user",
                "content": "explain data leakage in machine learning",
            }
        ],
    )
    assert any("one target class" in item for item in violations), violations

    # Dark scenes do not inherently establish higher GPU load/frame-rate drops.
    vrr_contract = AnswerContractRuntime(
        intent="factual_question",
        epistemic_mode="user_context_reasoning",
    )
    bad_vrr = (
        "It could still be VRR. In dark scenes the GPU is under heavier load rendering "
        "shadows and contrast, which causes frame-rate drops and visible flicker."
    )
    violations = find_user_diagnostic_overclaim_violations(
        user_input="could it still be VRR if the flicker only happens in dark scenes?",
        draft=bad_vrr,
        core_answer_contract=vrr_contract,
        conversation=[
            {
                "role": "user",
                "content": "why does my screen flicker when variable refresh rate is on?",
            }
        ],
    )
    assert any("dark scenes" in item and "GPU" in item for item in violations), violations

    # Personality cannot invent a long-running shared history.
    history = _unsupported_relationship_history_claims(
        draft="I've been processing your nonsense since before you had a name.",
        grounding_text="we've finally added developer diagnostics to you",
    )
    assert history, history

    # Nor can Mairon claim to be physically watching an unprovided clock.
    perception = _unsupported_mairon_perception_claims(
        "I'm just here watching the clock tick louder than your options."
    )
    assert perception, perception

    # Preserve labelled numeric relations from evidence. An ordinal round
    # number is not a vote count.
    packet = {
        "sources": [
            {
                "title": "Horikita Suzune's Choice",
                "search_snippet": "11th vote results: 1 in agreement, 38 in opposition.",
                "content_excerpt": "Results of the 11th round of voting: 1 in agreement, 38 in opposition.",
            }
        ]
    }
    bad_indexes = _deterministic_labeled_numeric_relation_indexes(
        packet,
        ["The result was 38 against her and only 11 in support."],
    )
    assert bad_indexes == {1}, bad_indexes
    assert not _deterministic_labeled_numeric_relation_indexes(
        packet,
        ["The result was 38 in opposition and 1 in agreement."],
    )
    retry = build_public_factual_retry_instruction([
        "public factual labelled numeric relation lacks source support: bad sentence"
    ])
    assert retry, retry

    print("Phase 11.6.6B28 manual acceptance closure: PASS")


if __name__ == "__main__":
    run()
