from dataclasses import dataclass
from typing import Any, Dict, Optional


WAKE_POLICY_ALWAYS_ASK = "always_ask"
WAKE_POLICY_NEVER = "never"

SUPPORTED_WAKE_POLICIES = {
    WAKE_POLICY_ALWAYS_ASK,
    WAKE_POLICY_NEVER,
}

DECISION_USE_DESKTOP = "use_desktop"
DECISION_WAKE_DESKTOP = "wake_desktop"
DECISION_ASK_TO_WAKE = "ask_to_wake"
DECISION_USE_ALTERNATIVE = "use_alternative"
DECISION_CONTINUE_WITHOUT_DESKTOP = "continue_without_desktop"
DECISION_DESKTOP_UNAVAILABLE = "desktop_unavailable"
DECISION_CAPABILITY_UNAVAILABLE = "desktop_capability_unavailable"


@dataclass(
    frozen=True
)
class DesktopNodeDecision:
    """
    Deterministic Core policy result for one potential desktop-node use.

    This object decides authority only. It does not send Wake-on-LAN packets,
    execute Desktop Agent actions, or grant itself any new capability.
    """

    decision: str
    desktop_online: bool
    desktop_required: bool
    explicit_wake_requested: bool
    wake_supported: bool
    requires_confirmation: bool
    should_wake: bool
    use_desktop: bool
    use_alternative: bool
    record_mairon_wake_ownership: bool
    node_id: Optional[str]
    reason: str

    def to_dict(
        self,
    ) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "desktop_online": self.desktop_online,
            "desktop_required": self.desktop_required,
            "explicit_wake_requested": (
                self.explicit_wake_requested
            ),
            "wake_supported": self.wake_supported,
            "requires_confirmation": (
                self.requires_confirmation
            ),
            "should_wake": self.should_wake,
            "use_desktop": self.use_desktop,
            "use_alternative": self.use_alternative,
            "record_mairon_wake_ownership": (
                self.record_mairon_wake_ownership
            ),
            "node_id": self.node_id,
            "reason": self.reason,
        }


def _normalise_wake_policy(
    wake_policy: str,
) -> str:
    value = str(
        wake_policy
        or WAKE_POLICY_ALWAYS_ASK
    ).strip().lower()

    if value not in SUPPORTED_WAKE_POLICIES:
        raise ValueError(
            "Unsupported desktop wake policy."
        )

    return value


def _extract_node(
    node_or_probe: Any,
) -> Optional[Dict[str, Any]]:
    """
    Accept either a raw descriptor or probe_desktop_node() style result.

    Only a structurally usable online descriptor is returned. Anything else
    is treated as unavailable; policy never fabricates node state.
    """

    if not isinstance(
        node_or_probe,
        dict,
    ):
        return None

    nested = node_or_probe.get(
        "node"
    )

    if isinstance(
        nested,
        dict,
    ):
        candidate = nested
    else:
        candidate = node_or_probe

    if candidate.get(
        "available"
    ) is not True:
        return None

    if str(
        candidate.get(
            "status",
            "",
        )
        or ""
    ).strip().lower() != "online":
        return None

    node_id = str(
        candidate.get(
            "node_id",
            "",
        )
        or ""
    ).strip()

    capabilities = candidate.get(
        "capabilities"
    )

    power = candidate.get(
        "power"
    )

    if (
        not node_id
        or not isinstance(
            capabilities,
            list,
        )
        or not isinstance(
            power,
            dict,
        )
    ):
        return None

    return candidate


def _node_has_capability(
    node: Optional[
        Dict[str, Any]
    ],
    required_capability: Optional[str],
) -> bool:
    if node is None:
        return False

    capability = str(
        required_capability
        or ""
    ).strip().lower()

    if not capability:
        return True

    capabilities = {
        str(
            item
            or ""
        ).strip().lower()
        for item in (
            node.get(
                "capabilities"
            )
            or []
        )
        if str(
            item
            or ""
        ).strip()
    }

    return capability in capabilities


def decide_desktop_node_use(
    node_or_probe: Any = None,
    *,
    desktop_required: bool,
    explicit_wake_requested: bool = False,
    alternative_available: bool = False,
    required_capability: Optional[str] = None,
    wake_supported: Optional[bool] = None,
    wake_policy: str = WAKE_POLICY_ALWAYS_ASK,
) -> DesktopNodeDecision:
    """
    Decide whether Core may use, wake, ask about, or avoid the desktop node.

    Intended policy:

        Desktop already online
        -> use it when appropriate.

        Desktop offline + explicit "turn my PC on"
        -> wake immediately, but only if wake authority actually exists.

        Desktop offline + task inherently requires the PC
        -> ask before waking under the default Always Ask policy.

        Desktop offline + Pi/cloud can complete the task
        -> use the alternative and leave the PC asleep.

    Wake-on-LAN itself is deliberately outside this module.
    """

    policy = _normalise_wake_policy(
        wake_policy
    )

    required = bool(
        desktop_required
    )

    explicit_wake = bool(
        explicit_wake_requested
    )

    alternative = bool(
        alternative_available
    )

    node = _extract_node(
        node_or_probe
    )

    online = node is not None

    node_id = None

    if node is not None:
        node_id = str(
            node.get(
                "node_id",
                "",
            )
            or ""
        ).strip() or None

    if wake_supported is None:
        wake_capability = bool(
            (
                node.get(
                    "power"
                )
                or {}
            ).get(
                "wake_supported",
                False,
            )
        ) if node is not None else False

    else:
        wake_capability = bool(
            wake_supported
        )

    if online:
        if _node_has_capability(
            node,
            required_capability,
        ):
            return DesktopNodeDecision(
                decision=DECISION_USE_DESKTOP,
                desktop_online=True,
                desktop_required=required,
                explicit_wake_requested=explicit_wake,
                wake_supported=wake_capability,
                requires_confirmation=False,
                should_wake=False,
                use_desktop=True,
                use_alternative=False,
                record_mairon_wake_ownership=False,
                node_id=node_id,
                reason=(
                    "The desktop node is already online and advertises "
                    "the required capability."
                ),
            )

        if alternative:
            return DesktopNodeDecision(
                decision=DECISION_USE_ALTERNATIVE,
                desktop_online=True,
                desktop_required=required,
                explicit_wake_requested=explicit_wake,
                wake_supported=wake_capability,
                requires_confirmation=False,
                should_wake=False,
                use_desktop=False,
                use_alternative=True,
                record_mairon_wake_ownership=False,
                node_id=node_id,
                reason=(
                    "The online desktop does not advertise the required "
                    "capability, but an approved alternative is available."
                ),
            )

        return DesktopNodeDecision(
            decision=DECISION_CAPABILITY_UNAVAILABLE,
            desktop_online=True,
            desktop_required=required,
            explicit_wake_requested=explicit_wake,
            wake_supported=wake_capability,
            requires_confirmation=False,
            should_wake=False,
            use_desktop=False,
            use_alternative=False,
            record_mairon_wake_ownership=False,
            node_id=node_id,
            reason=(
                "The desktop is online but does not advertise the required "
                "capability."
            ),
        )

    # --------------------------------------------------
    # Desktop is offline/unreachable from Core.
    # --------------------------------------------------

    if explicit_wake:
        if wake_capability:
            return DesktopNodeDecision(
                decision=DECISION_WAKE_DESKTOP,
                desktop_online=False,
                desktop_required=required,
                explicit_wake_requested=True,
                wake_supported=True,
                requires_confirmation=False,
                should_wake=True,
                use_desktop=False,
                use_alternative=False,
                record_mairon_wake_ownership=True,
                node_id=None,
                reason=(
                    "The user explicitly requested the desktop be turned on, "
                    "so no additional wake confirmation is required."
                ),
            )

        return DesktopNodeDecision(
            decision=DECISION_DESKTOP_UNAVAILABLE,
            desktop_online=False,
            desktop_required=required,
            explicit_wake_requested=True,
            wake_supported=False,
            requires_confirmation=False,
            should_wake=False,
            use_desktop=False,
            use_alternative=False,
            record_mairon_wake_ownership=False,
            node_id=None,
            reason=(
                "The user explicitly requested a desktop wake, but Core has "
                "no configured wake authority yet."
            ),
        )

    if required:
        if wake_capability:
            if (
                policy
                == WAKE_POLICY_ALWAYS_ASK
            ):
                return DesktopNodeDecision(
                    decision=DECISION_ASK_TO_WAKE,
                    desktop_online=False,
                    desktop_required=True,
                    explicit_wake_requested=False,
                    wake_supported=True,
                    requires_confirmation=True,
                    should_wake=False,
                    use_desktop=False,
                    use_alternative=False,
                    record_mairon_wake_ownership=False,
                    node_id=None,
                    reason=(
                        "The task requires the desktop and it is offline; "
                        "the default wake policy requires confirmation."
                    ),
                )

            return DesktopNodeDecision(
                decision=DECISION_DESKTOP_UNAVAILABLE,
                desktop_online=False,
                desktop_required=True,
                explicit_wake_requested=False,
                wake_supported=True,
                requires_confirmation=False,
                should_wake=False,
                use_desktop=False,
                use_alternative=False,
                record_mairon_wake_ownership=False,
                node_id=None,
                reason=(
                    "The task requires the offline desktop, but the active "
                    "wake policy does not permit waking it."
                ),
            )

        return DesktopNodeDecision(
            decision=DECISION_DESKTOP_UNAVAILABLE,
            desktop_online=False,
            desktop_required=True,
            explicit_wake_requested=False,
            wake_supported=False,
            requires_confirmation=False,
            should_wake=False,
            use_desktop=False,
            use_alternative=False,
            record_mairon_wake_ownership=False,
            node_id=None,
            reason=(
                "The task requires the desktop, but it is offline and no "
                "desktop wake mechanism is currently configured."
            ),
        )

    if alternative:
        return DesktopNodeDecision(
            decision=DECISION_USE_ALTERNATIVE,
            desktop_online=False,
            desktop_required=False,
            explicit_wake_requested=False,
            wake_supported=wake_capability,
            requires_confirmation=False,
            should_wake=False,
            use_desktop=False,
            use_alternative=True,
            record_mairon_wake_ownership=False,
            node_id=None,
            reason=(
                "The desktop is offline, but an approved Pi/cloud/local "
                "alternative can complete the task without waking it."
            ),
        )

    return DesktopNodeDecision(
        decision=DECISION_CONTINUE_WITHOUT_DESKTOP,
        desktop_online=False,
        desktop_required=False,
        explicit_wake_requested=False,
        wake_supported=wake_capability,
        requires_confirmation=False,
        should_wake=False,
        use_desktop=False,
        use_alternative=False,
        record_mairon_wake_ownership=False,
        node_id=None,
        reason=(
            "The current task does not require the desktop, so Core leaves "
            "the offline node asleep."
        ),
    )
