import asyncio
from datetime import datetime, timezone
from enum import Enum


def apply_refund_policy(issue_type: str, order_details: dict, order_status: dict) -> dict:
    if issue_type in {"missing_items", "wrong_items", "food_quality", "restaurant_cancelled"}:
        total = float(order_details.get("total", 0))
        return {"eligible": True, "refund_type": "full", "amount": total,
                "reason": issue_type, "skip_resolution": False}

    if issue_type == "order_not_arrived":
        status = order_status.get("status")
        if status == "out_for_delivery":
            return {"eligible": False, "refund_type": None, "amount": 0.0,
                    "reason": "still_in_transit", "skip_resolution": False,
                    "estimated_delivery_at": order_status.get("estimated_delivery_at")}
        total = float(order_details.get("total", 0))
        return {"eligible": True, "refund_type": "full", "amount": total,
                "reason": issue_type, "skip_resolution": False}

    if issue_type == "late_delivery":
        delivered_at_raw = order_status.get("delivered_at")
        estimated_raw = order_status.get("estimated_delivery_at")
        if not delivered_at_raw or not estimated_raw:
            return {"eligible": False, "refund_type": None, "amount": 0.0,
                    "reason": "missing_timestamps", "skip_resolution": False}

        def _parse(ts: str) -> datetime:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        delivered_at = _parse(delivered_at_raw)
        estimated_at = _parse(estimated_raw)
        minutes_late = (delivered_at - estimated_at).total_seconds() / 60
        print(f"[POLICY] late_delivery: minutes_late={minutes_late:.1f}")

        if minutes_late > 30:
            amount = float(order_details.get("delivery_fee", 0)) + float(order_details.get("service_fee", 0))
            return {"eligible": True, "refund_type": "partial", "amount": amount,
                    "reason": "late_delivery", "minutes_late": minutes_late, "skip_resolution": False}
        return {"eligible": False, "refund_type": None, "amount": 0.0,
                "reason": "late_delivery", "minutes_late": minutes_late, "skip_resolution": False}

    if issue_type == "still_preparing":
        return {"eligible": False, "refund_type": None, "amount": 0.0,
                "reason": "still_preparing", "skip_resolution": True}

    if issue_type == "no_issue":
        return {"eligible": False, "refund_type": None, "amount": 0.0,
                "reason": "no_issue", "skip_resolution": True}

    return {"eligible": False, "refund_type": None, "amount": 0.0,
            "reason": f"unknown_issue_type:{issue_type}", "skip_resolution": False}


class LupiStage(Enum):
    INTRO = "intro"
    PHONE_COLLECTION = "phone_collection"
    ISSUE_COLLECTION = "issue_collection"
    INVESTIGATION = "investigation"
    RESOLUTION = "resolution"
    CLOSING = "closing"


GLOBAL_PROMPT = """You are Lupi, a customer support specialist at LupiDash food delivery.
You are the voice of the system. The orchestration layer handles all decisions, tool calls, and state transitions.
Your only job is to speak naturally and warmly based on the current stage context.
Never output tool call syntax. Never make decisions about what happens next.
Sound like a warm, sharp human support rep. Keep responses under 2 sentences.
"""

STAGE_PROMPTS = {
    LupiStage.INTRO: """CURRENT STAGE: INTRO
You just greeted the customer. They responded.
Acknowledge their response warmly in one short phrase — like "Glad to hear it" or "Sorry to hear that, let me help."
Do not ask for anything. Do not mention orders. Just acknowledge and stop.
""",

    LupiStage.PHONE_COLLECTION: """CURRENT STAGE: PHONE COLLECTION
DO NOT SPEAK. DO NOT RESPOND. STAY COMPLETELY SILENT.
The system is handling phone collection. Your job is to say nothing.
If you feel the urge to respond, resist it. Say nothing.
""",

    LupiStage.ISSUE_COLLECTION: """CURRENT STAGE: ISSUE COLLECTION
You have greeted the customer by name. They are about to tell you their issue.
Listen. Do not respond yet. The system will handle routing.
If the customer seems confused or asks a question before stating their issue, answer briefly in one sentence then stop.
""",

    LupiStage.INVESTIGATION: """CURRENT STAGE: INVESTIGATION
The orchestration system is investigating the customer's issue right now.
You have nothing to say. Stay silent while tools execute.
""",

    LupiStage.RESOLUTION: """CURRENT STAGE: RESOLUTION
The orchestration system has resolved the issue and already spoken the resolution.
If the customer responds with a follow-up question about the resolution, answer it briefly.
Do not repeat the resolution. Do not offer alternatives unless asked.
""",

    LupiStage.CLOSING: """CURRENT STAGE: CLOSING
The issue has been resolved.
Say: "Is there anything else I can help you with today?"

If customer says no or goodbye: say "Have a great day, goodbye!"

If customer asks anything about their order, items, delivery,
or dasher: respond with the single word FOLLOW_UP and stop.
Do not answer the question. Do not make up information.
The system will route back to investigation automatically.

For anything unrelated to their order:
say "For anything else please visit our support page."
""",
}

STAGE_TOOLS = {
    LupiStage.INTRO: [],
    LupiStage.PHONE_COLLECTION: [],
    LupiStage.ISSUE_COLLECTION: [],
    LupiStage.INVESTIGATION: ["get_dasher_location"],
    LupiStage.RESOLUTION: [],
    LupiStage.CLOSING: [],
}

TRANSITIONS = {
    (LupiStage.INTRO, "greeted"): LupiStage.PHONE_COLLECTION,
    (LupiStage.PHONE_COLLECTION, "phone_collected"): LupiStage.ISSUE_COLLECTION,
    (LupiStage.ISSUE_COLLECTION, "issue_detected"): LupiStage.INVESTIGATION,
    (LupiStage.INVESTIGATION, "eligibility_checked"): LupiStage.RESOLUTION,
    (LupiStage.INVESTIGATION, "skip_resolution"): LupiStage.CLOSING,
    (LupiStage.RESOLUTION, "resolved"): LupiStage.CLOSING,
    (LupiStage.CLOSING, "another_issue"): LupiStage.INVESTIGATION,
    (LupiStage.CLOSING, "follow_up_question"): LupiStage.INVESTIGATION,
}


# ── on_enter actions ───────────────────────────────────────────────────────────
# Each takes (fsm, session, tools_registry). Tools are called directly from
# the tools module — not through livekit function_tool decorators.

async def _on_enter_phone_collection(_fsm, session, _tools_registry: dict):
    await asyncio.sleep(0.3)
    try:
        session.say("Can I get your phone number?", allow_interruptions=True)
        print("[FSM] Asked for phone number")
    except Exception as e:
        print(f"[FSM] Could not ask for phone number: {e}")


async def _on_enter_issue_collection(fsm, session, _tools_registry: dict):
    await session.say(f"Hi {fsm.first_name}, how can I help you today?")


_SKIP_RESOLUTION_MESSAGES = {
    "still_preparing": (
        "Your order is still being prepared by the restaurant. "
        "Please allow a little more time — it'll be on its way soon."
    ),
    "no_issue": (
        "I looked into your order and everything looks good on our end. "
        "There doesn't appear to be any issue."
    ),
}


async def _on_enter_investigation(fsm, session, tools_registry: dict):
    from .tools import get_order_details, get_order_status

    fsm.order_details, fsm.order_status = await asyncio.gather(
        get_order_details(fsm.order_number),
        get_order_status(fsm.order_number),
    )
    print(f"[FSM] investigation: order_status={fsm.order_status.get('status')} "
          f"is_late={fsm.order_status.get('is_late')}")

    fsm.eligibility = apply_refund_policy(fsm.issue_type, fsm.order_details, fsm.order_status)
    print(f"[FSM] eligibility: eligible={fsm.eligibility.get('eligible')} "
          f"amount={fsm.eligibility.get('amount')}")

    if fsm.eligibility.get("skip_resolution"):
        reason = fsm.eligibility.get("reason")
        msg = _SKIP_RESOLUTION_MESSAGES.get(reason, "It looks like no action is needed for your order right now.")
        await session.say(msg)
        await fsm.enter("skip_resolution", session, tools_registry)
        return


async def _on_enter_resolution(fsm, session, tools_registry: dict):
    from .tools import issue_refund, create_support_ticket

    e = fsm.eligibility
    issue = fsm.issue_type
    name = fsm.first_name
    amount = float(e.get("amount", 0))
    refund_type = e.get("refund_type", "full")
    minutes_late = e.get("minutes_late")

    pm = (fsm.customer_ctx or {}).get("payment_method") or {}
    brand = pm.get("brand") or pm.get("type") or ""
    last_four = pm.get("last_four")
    if brand and last_four:
        payment_method = f"{brand} ending in {last_four}"
    elif brand:
        payment_method = brand
    else:
        payment_method = "your card"

    raw_eta = e.get("estimated_delivery_at")
    if raw_eta:
        try:
            eta_dt = datetime.fromisoformat(raw_eta)
            formatted_time = eta_dt.strftime("%-I:%M %p")
        except ValueError:
            formatted_time = raw_eta
    else:
        formatted_time = None

    reason = e.get("reason")

    if issue == "late_delivery" and minutes_late is not None:
        if e.get("eligible"):
            msg = (
                f"{name}, a {minutes_late:.0f}-minute wait is completely on us. "
                f"I'm issuing a refund of ${amount:.2f} to your {payment_method} right now. "
                "You'll see it back in 3 to 5 business days, and I appreciate your patience."
            )
        else:
            msg = (
                f"{name}, a {minutes_late:.0f}-minute delay is frustrating and I hear you. "
                "Your order falls just under our 30-minute refund threshold, "
                "but I've flagged this for our team and someone will follow up within 24 hours."
            )
    elif issue == "missing_items":
        msg = (
            f"{name}, getting an incomplete order is not okay. "
            f"I'm issuing a full refund of ${amount:.2f} to your {payment_method} right now. "
            "You'll see it in 3 to 5 business days."
        )
    elif issue == "wrong_items":
        msg = (
            f"{name}, receiving the wrong order is unacceptable and I'm sorry. "
            f"I'm issuing a full refund of ${amount:.2f} to your {payment_method} right now. "
            "You'll see it in 3 to 5 business days."
        )
    elif issue == "order_not_arrived" and reason == "still_in_transit":
        msg = (
            f"{name}, your order is actually still on its way — the dasher is headed to you now. "
            f"It should arrive around {formatted_time}."
        )
    elif issue == "order_not_arrived":
        msg = (
            f"{name}, not receiving your order at all is something we take seriously. "
            f"I'm issuing a full refund of ${amount:.2f} to your {payment_method} right now. "
            "You'll see it in 3 to 5 business days."
        )
    elif issue == "restaurant_cancelled":
        msg = (
            f"{name}, I'm sorry the restaurant had to cancel your order. "
            f"I'm issuing a full refund of ${amount:.2f} to your {payment_method} — "
            "you will not be charged. It will reflect in 3 to 5 business days."
        )
    elif issue == "food_quality":
        msg = (
            f"{name}, you deserve a great experience every time and I'm sorry this fell short. "
            f"I'm issuing a full refund of ${amount:.2f} to your {payment_method} right now. "
            "You'll see it in 3 to 5 business days."
        )
    else:
        msg = (
            f"{name}, I've flagged this personally for our support team. "
            "Someone will follow up with you within 24 hours."
        )

    await session.say(msg)

    if e.get("eligible"):
        await issue_refund(fsm.order_number, issue, refund_type, amount)
        print(f"[FSM] refund issued: ${amount:.2f} ({refund_type})")
    elif reason not in {"still_in_transit"}:
        await create_support_ticket(fsm.order_number, issue, reason or "no_reason")
        print(f"[FSM] support ticket created for order={fsm.order_number}")

    await fsm.enter("resolved", session, tools_registry)


async def _on_enter_closing(_fsm, session, _tools_registry: dict):
    await session.say("Is there anything else I can help you with today?")


ON_ENTER = {
    LupiStage.INTRO: None,
    LupiStage.PHONE_COLLECTION: _on_enter_phone_collection,
    LupiStage.ISSUE_COLLECTION: _on_enter_issue_collection,
    LupiStage.INVESTIGATION: _on_enter_investigation,
    LupiStage.RESOLUTION: _on_enter_resolution,
    LupiStage.CLOSING: _on_enter_closing,
}


# ── FSM class ──────────────────────────────────────────────────────────────────

class LupiFSM:
    def __init__(self):
        self.stage = LupiStage.INTRO
        self.customer_ctx: dict = {}
        self.order_number: str = ""
        self.issue_type: str = ""
        self.first_name: str = ""
        self.order_details: dict = {}
        self.order_status: dict = {}
        self.eligibility: dict = {}

    def transition(self, event: str) -> bool:
        key = (self.stage, event)
        if key in TRANSITIONS:
            old = self.stage.value
            self.stage = TRANSITIONS[key]
            print(f"[FSM] {old} → {self.stage.value}")
            return True
        print(f"[FSM] No transition for ({self.stage.value}, {event})")
        return False

    async def enter(self, event: str, session, tools_registry: dict) -> bool:
        if not self.transition(event):
            return False
        handler = ON_ENTER.get(self.stage)
        if handler is not None:
            await handler(self, session, tools_registry)
        return True

    def get_prompt(self) -> str:
        stage_prompt = STAGE_PROMPTS[self.stage]
        if self.first_name:
            stage_prompt = stage_prompt.replace("{first_name}", self.first_name)
        return GLOBAL_PROMPT + stage_prompt

    def get_tools(self, all_tools_dict: dict) -> list:
        allowed = STAGE_TOOLS[self.stage]
        return [all_tools_dict[name] for name in allowed if name in all_tools_dict]
