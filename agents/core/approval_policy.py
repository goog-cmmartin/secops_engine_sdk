"""Server-side approval policy for change proposals.

Decides the authority tier a proposal requires and whether a given approver may
merge it. Enforced inside ``ProposalManager.approve_and_merge`` so every caller
(REST API, chat, scripts) is subject to the same rules.

Rules:
  * Nobody may approve a proposal they authored.
  * TIER_3_HUMAN_APPROVAL proposals cannot be approved by an agent handle.
  * Code-change proposals (rule text, parser CBN) whose syntax preflight failed
    are blocked unless a human approver supplies an explicit override reason.
"""

from typing import Optional

from engine.domain import AuthorityTier

# Actions that change what runs in production (deployment state) or execute an
# arbitrary engine capability. Always require a human.
HUMAN_ONLY_ACTIONS = frozenset({
    "DEPLOY_RULE",
    "UNDEPLOY_RULE",
    "UPDATE_RULE_DEPLOYMENT",
    "TOGGLE_RULE_DEPLOYMENT",
    "GENERIC_CAPABILITY",
})

# Actions whose payload is code that a compiler preflight can verify.
CODE_CHANGE_ACTIONS = frozenset({
    "PATCH_RULE",
    "UPDATE_RULE_TEXT",
    "PATCH_PARSER_CBN",
})

HIGH_RISK_LEVELS = frozenset({"HIGH", "CRITICAL"})

MIN_OVERRIDE_REASON_LEN = 10

_TIER_RANK = {
    AuthorityTier.TIER_1_AUTONOMOUS.value: 1,
    AuthorityTier.TIER_2_PEER_REVIEW.value: 2,
    AuthorityTier.TIER_3_HUMAN_APPROVAL.value: 3,
}


class ApprovalPolicyError(Exception):
    """Raised when an approval violates policy. ``code`` is machine-readable."""

    SELF_APPROVAL = "SELF_APPROVAL"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    OVERRIDE_REASON_REQUIRED = "OVERRIDE_REASON_REQUIRED"

    def __init__(self, code: str, message: str, required_tier: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.required_tier = required_tier

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "required_tier": self.required_tier}


def _normalize_actor(actor: Optional[str]) -> str:
    return (actor or "").strip().lstrip("@").lower()


def is_agent_actor(actor: Optional[str]) -> bool:
    """Agent handles are '@'-prefixed by convention throughout the fleet."""
    return (actor or "").strip().startswith("@")


def required_tier(action_type: str, risk_level: str) -> str:
    """Computes the minimum authority tier for an action. Never returns TIER_1."""
    action = (action_type or "").upper()
    risk = (risk_level or "").upper()
    if action in HUMAN_ONLY_ACTIONS or risk in HIGH_RISK_LEVELS:
        return AuthorityTier.TIER_3_HUMAN_APPROVAL.value
    return AuthorityTier.TIER_2_PEER_REVIEW.value


def effective_tier(stored_tier: Optional[str], action_type: str, risk_level: str) -> str:
    """The stricter of the stored tier and the computed tier.

    A stored tier can raise the bar but never lower it below what the action
    requires, so an agent cannot self-declare TIER_1.
    """
    computed = required_tier(action_type, risk_level)
    if stored_tier and _TIER_RANK.get(stored_tier, 0) > _TIER_RANK[computed]:
        return stored_tier
    return computed


def check_approval(
    *,
    author: str,
    approver: str,
    action_type: str,
    risk_level: str,
    stored_tier: Optional[str],
    syntax_verified: bool,
    override_preflight: bool = False,
    override_reason: Optional[str] = None,
) -> str:
    """Validates an approval. Returns the effective tier or raises ApprovalPolicyError."""
    tier = effective_tier(stored_tier, action_type, risk_level)

    if _normalize_actor(approver) and _normalize_actor(approver) == _normalize_actor(author):
        raise ApprovalPolicyError(
            ApprovalPolicyError.SELF_APPROVAL,
            f"{approver} authored this proposal and cannot approve it.",
            tier,
        )

    if tier == AuthorityTier.TIER_3_HUMAN_APPROVAL.value and is_agent_actor(approver):
        raise ApprovalPolicyError(
            ApprovalPolicyError.HUMAN_REQUIRED,
            f"{action_type} ({risk_level} risk) requires human approval; agent {approver} cannot approve it.",
            tier,
        )

    if (action_type or "").upper() in CODE_CHANGE_ACTIONS and not syntax_verified:
        if not override_preflight:
            raise ApprovalPolicyError(
                ApprovalPolicyError.PREFLIGHT_FAILED,
                "Syntax preflight did not pass. Approving requires an explicit override with a reason.",
                tier,
            )
        if is_agent_actor(approver):
            raise ApprovalPolicyError(
                ApprovalPolicyError.HUMAN_REQUIRED,
                "Only a human approver can override a failed preflight.",
                tier,
            )
        if len((override_reason or "").strip()) < MIN_OVERRIDE_REASON_LEN:
            raise ApprovalPolicyError(
                ApprovalPolicyError.OVERRIDE_REASON_REQUIRED,
                f"Preflight override requires a reason of at least {MIN_OVERRIDE_REASON_LEN} characters.",
                tier,
            )

    return tier
