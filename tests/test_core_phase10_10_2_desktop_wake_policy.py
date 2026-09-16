import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

SRC_DIR = PROJECT_ROOT / "src"

if str(
    SRC_DIR
) not in sys.path:
    sys.path.insert(
        0,
        str(
            SRC_DIR
        ),
    )


from core.desktop_agent_protocol import (
    build_desktop_node_descriptor,
)
from core.desktop_node_policy import (
    DECISION_ASK_TO_WAKE,
    DECISION_CAPABILITY_UNAVAILABLE,
    DECISION_CONTINUE_WITHOUT_DESKTOP,
    DECISION_DESKTOP_UNAVAILABLE,
    DECISION_USE_ALTERNATIVE,
    DECISION_USE_DESKTOP,
    DECISION_WAKE_DESKTOP,
    WAKE_POLICY_NEVER,
    decide_desktop_node_use,
)


def run():
    node = build_desktop_node_descriptor(
        node_id="policy_test_desktop"
    )

    # --------------------------------------------------
    # 1. Online capable desktop is used without wake/confirmation.
    # --------------------------------------------------

    online = decide_desktop_node_use(
        node,
        desktop_required=True,
        required_capability="application_control",
    )

    assert online.decision == DECISION_USE_DESKTOP
    assert online.desktop_online is True
    assert online.use_desktop is True
    assert online.should_wake is False
    assert online.requires_confirmation is False
    assert online.record_mairon_wake_ownership is False

    # --------------------------------------------------
    # 2. Missing online capability fails closed.
    # --------------------------------------------------

    missing = decide_desktop_node_use(
        node,
        desktop_required=True,
        required_capability="gpu_heavy_compute",
    )

    assert (
        missing.decision
        == DECISION_CAPABILITY_UNAVAILABLE
    )

    assert missing.use_desktop is False

    # If an approved alternative exists, prefer it instead of pretending the
    # desktop supports a capability it never advertised.
    missing_with_alternative = decide_desktop_node_use(
        node,
        desktop_required=False,
        alternative_available=True,
        required_capability="gpu_heavy_compute",
    )

    assert (
        missing_with_alternative.decision
        == DECISION_USE_ALTERNATIVE
    )

    # --------------------------------------------------
    # 3. Explicit wake request bypasses confirmation only when wake exists.
    # --------------------------------------------------

    explicit_wake = decide_desktop_node_use(
        None,
        desktop_required=False,
        explicit_wake_requested=True,
        wake_supported=True,
    )

    assert (
        explicit_wake.decision
        == DECISION_WAKE_DESKTOP
    )

    assert explicit_wake.should_wake is True
    assert explicit_wake.requires_confirmation is False
    assert (
        explicit_wake.record_mairon_wake_ownership
        is True
    )

    # Current real 10.10.1 state: WOL is not configured, so Core must not
    # claim it can turn the machine on yet.
    explicit_without_wol = decide_desktop_node_use(
        None,
        desktop_required=False,
        explicit_wake_requested=True,
        wake_supported=False,
    )

    assert (
        explicit_without_wol.decision
        == DECISION_DESKTOP_UNAVAILABLE
    )

    assert explicit_without_wol.should_wake is False

    # --------------------------------------------------
    # 4. Offline desktop-required task asks before waking by default.
    # --------------------------------------------------

    required_offline = decide_desktop_node_use(
        None,
        desktop_required=True,
        wake_supported=True,
    )

    assert (
        required_offline.decision
        == DECISION_ASK_TO_WAKE
    )

    assert required_offline.requires_confirmation is True
    assert required_offline.should_wake is False
    assert (
        required_offline.record_mairon_wake_ownership
        is False
    )

    # --------------------------------------------------
    # 5. "Never wake" policy denies implied wake authority.
    # --------------------------------------------------

    never = decide_desktop_node_use(
        None,
        desktop_required=True,
        wake_supported=True,
        wake_policy=WAKE_POLICY_NEVER,
    )

    assert (
        never.decision
        == DECISION_DESKTOP_UNAVAILABLE
    )

    assert never.requires_confirmation is False
    assert never.should_wake is False

    # Explicit wake remains explicit user authority even under Always Ask /
    # Never automatic policies. The policy only blocks implied wakes.
    explicit_under_never = decide_desktop_node_use(
        None,
        desktop_required=True,
        explicit_wake_requested=True,
        wake_supported=True,
        wake_policy=WAKE_POLICY_NEVER,
    )

    assert (
        explicit_under_never.decision
        == DECISION_WAKE_DESKTOP
    )

    # --------------------------------------------------
    # 6. Offline task with an alternative never wakes the PC.
    # --------------------------------------------------

    alternative = decide_desktop_node_use(
        None,
        desktop_required=False,
        alternative_available=True,
        wake_supported=True,
    )

    assert (
        alternative.decision
        == DECISION_USE_ALTERNATIVE
    )

    assert alternative.should_wake is False
    assert alternative.use_alternative is True

    # --------------------------------------------------
    # 7. Ordinary Pi/Core work leaves the offline desktop asleep.
    # --------------------------------------------------

    no_desktop_needed = decide_desktop_node_use(
        None,
        desktop_required=False,
        alternative_available=False,
        wake_supported=True,
    )

    assert (
        no_desktop_needed.decision
        == DECISION_CONTINUE_WITHOUT_DESKTOP
    )

    assert no_desktop_needed.should_wake is False

    # --------------------------------------------------
    # 8. Invalid/untrusted descriptors are treated as unavailable.
    # --------------------------------------------------

    malformed = {
        "node_id": "fake",
        "available": True,
        "status": "online",
        "capabilities": "arbitrary_shell",
        "power": {
            "wake_supported": True,
        },
    }

    malformed_decision = decide_desktop_node_use(
        malformed,
        desktop_required=True,
        wake_supported=False,
    )

    assert (
        malformed_decision.decision
        == DECISION_DESKTOP_UNAVAILABLE
    )

    assert malformed_decision.use_desktop is False

    print(
        "Mairon Phase 10.10.2 desktop wake-decision policy tests: PASS"
    )


if __name__ == "__main__":
    run()
