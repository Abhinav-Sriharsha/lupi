"""
Lupi agent tool layer.

All functions are async and return clean dicts — no side-effect prints.
Supabase queries are run via the synchronous client wrapped in asyncio.to_thread
so they do not block the LiveKit event loop.
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client

# ── Bootstrap ──────────────────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent          # backend/lupi/
load_dotenv(dotenv_path=_here.parent / ".env")   # backend/.env

supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_SERVICE_KEY", ""),
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(fn, *args, **kwargs):
    """Run a synchronous supabase call in a thread so the event loop stays free."""
    return asyncio.to_thread(fn, *args, **kwargs)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Supabase returns ISO-8601 with timezone
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minutes_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60, 1)


VALID_REASONS = {
    "late_delivery",
    "missing_items",
    "wrong_items",
    "order_not_arrived",
    "food_quality",
    "restaurant_cancelled",
}

# ── 1. get_customer_context ────────────────────────────────────────────────────

async def get_customer_context(phone: str) -> dict:
    """
    Returns full customer context needed by the agent at call start.
    Looks up by phone, then fetches their default address, default payment
    method, and 3 most-recent orders.
    """
    import re
    digits = re.sub(r'\D', '', phone)
    # Strip leading 1 if 11 digits starting with 1
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        phone = f"+1{digits}"
    print(f"[TOOLS] phone normalized to: {phone}")

    # Customer
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_customers")
            .select("*")
            .eq("phone", phone)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"error": "customer_not_found"}

    cust = resp.data[0]
    cid  = cust["id"]

    # Default address
    addr_resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_addresses")
            .select("label,street,city,state,zip,delivery_instructions")
            .eq("customer_id", cid)
            .eq("is_default", True)
            .limit(1)
            .execute()
    )
    address = addr_resp.data[0] if addr_resp.data else None

    # Default payment method
    pm_resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_payment_methods")
            .select("type,brand,last_four")
            .eq("customer_id", cid)
            .eq("is_default", True)
            .limit(1)
            .execute()
    )
    payment_method = pm_resp.data[0] if pm_resp.data else None

    # 3 most recent orders — join restaurant name manually
    orders_resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select("order_number,status,restaurant_id,total,placed_at")
            .eq("customer_id", cid)
            .order("placed_at", desc=True)
            .limit(3)
            .execute()
    )
    recent_orders = []
    for o in (orders_resp.data or []):
        rest_name = None
        if o.get("restaurant_id"):
            r_resp = await asyncio.to_thread(
                lambda rid=o["restaurant_id"]: supabase.table("lupi_restaurants")
                    .select("name")
                    .eq("id", rid)
                    .limit(1)
                    .execute()
            )
            if r_resp.data:
                rest_name = r_resp.data[0]["name"]
        recent_orders.append({
            "order_number": o["order_number"],
            "status":       o["status"],
            "restaurant":   rest_name,
            "total":        o["total"],
            "placed_at":    o["placed_at"],
        })

    return {
        "customer_id":       cid,
        "full_name":         f"{cust['first_name']} {cust['last_name']}",
        "phone":             cust["phone"],
        "email":             cust["email"],
        "is_dashpass_member": cust["is_dashpass_member"],
        "credits_balance":   cust["credits_balance"],
        "total_orders":      cust["total_orders"],
        "address":           address,
        "payment_method":    payment_method,
        "recent_orders":     recent_orders,
    }

# ── 2. get_order_details ───────────────────────────────────────────────────────

async def get_order_details(order_number: str) -> dict:
    """
    Full snapshot of an order: restaurant, dasher, line items, financials,
    timing, and any special instructions or cancellation reason.
    """
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select("*")
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"error": "order_not_found"}

    order = resp.data[0]

    # Restaurant name
    rest_name = None
    if order.get("restaurant_id"):
        r = await asyncio.to_thread(
            lambda: supabase.table("lupi_restaurants")
                .select("name")
                .eq("id", order["restaurant_id"])
                .limit(1)
                .execute()
        )
        if r.data:
            rest_name = r.data[0]["name"]

    # Dasher info
    dasher_name    = None
    dasher_vehicle = None
    if order.get("dasher_id"):
        d = await asyncio.to_thread(
            lambda: supabase.table("lupi_dashers")
                .select("first_name,vehicle_type")
                .eq("id", order["dasher_id"])
                .limit(1)
                .execute()
        )
        if d.data:
            dasher_name    = d.data[0]["first_name"]
            dasher_vehicle = d.data[0]["vehicle_type"]

    # Order items
    items_resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_order_items")
            .select("name,quantity,unit_price,notes,customizations")
            .eq("order_id", order["id"])
            .execute()
    )
    items = items_resp.data or []

    # Delivery address street
    address_street = None
    if order.get("delivery_address_id"):
        a = await asyncio.to_thread(
            lambda: supabase.table("lupi_addresses")
                .select("street,city,state,zip")
                .eq("id", order["delivery_address_id"])
                .limit(1)
                .execute()
        )
        if a.data:
            row = a.data[0]
            address_street = f"{row['street']}, {row['city']}, {row['state']} {row['zip']}"

    return {
        "order_number":          order["order_number"],
        "status":                order["status"],
        "restaurant_name":       rest_name,
        "dasher_name":           dasher_name,
        "dasher_vehicle":        dasher_vehicle,
        "items":                 items,
        "subtotal":              order["subtotal"],
        "delivery_fee":          order["delivery_fee"],
        "service_fee":           order["service_fee"],
        "tip":                   order["tip"],
        "total":                 order["total"],
        "delivery_address":      address_street,
        "placed_at":             order["placed_at"],
        "estimated_delivery_at": order["estimated_delivery_at"],
        "delivered_at":          order.get("delivered_at"),
        "special_instructions":  order.get("special_instructions"),
        "cancellation_reason":   order.get("cancellation_reason"),
    }

# ── 3. get_order_status ────────────────────────────────────────────────────────

async def get_order_status(order_number: str) -> dict:
    """
    Lightweight status + timing snapshot. Calculates lateness and elapsed time.
    """
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select(
                "order_number,status,placed_at,estimated_pickup_at,"
                "picked_up_at,estimated_delivery_at,delivered_at,"
                "cancelled_at,cancellation_reason"
            )
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"error": "order_not_found"}

    o = resp.data[0]
    placed_dt       = _parse_dt(o["placed_at"])
    est_delivery_dt = _parse_dt(o["estimated_delivery_at"])
    delivered_dt    = _parse_dt(o.get("delivered_at"))
    picked_up_dt    = _parse_dt(o.get("picked_up_at"))

    minutes_late         = None
    is_late              = False
    minutes_since_placed = _minutes_between(placed_dt, _now())

    if delivered_dt and est_delivery_dt:
        diff = _minutes_between(est_delivery_dt, delivered_dt)
        if diff is not None and diff > 10:
            is_late      = True
            minutes_late = diff
    elif o["status"] == "out_for_delivery" and est_delivery_dt:
        # Still in transit — check if past estimated delivery
        diff = _minutes_between(est_delivery_dt, _now())
        if diff is not None and diff > 10:
            is_late      = True
            minutes_late = diff

    return {
        "order_number":          o["order_number"],
        "status":                o["status"],
        "placed_at":             o["placed_at"],
        "estimated_delivery_at": o["estimated_delivery_at"],
        "delivered_at":          o.get("delivered_at"),
        "picked_up_at":          o.get("picked_up_at"),
        "cancelled_at":          o.get("cancelled_at"),
        "is_late":               is_late,
        "minutes_late":          minutes_late,
        "minutes_since_placed":  minutes_since_placed,
        "cancellation_reason":   o.get("cancellation_reason"),
    }

# ── 4. check_refund_eligibility ────────────────────────────────────────────────

async def check_refund_eligibility(order_number: str, reason: str) -> dict:
    """
    Evaluates whether a refund can be issued given the order state and reason.
    Returns eligibility verdict, refund type, and estimated amount.
    """
    if reason not in VALID_REASONS:
        return {
            "eligible":         False,
            "reason":           reason,
            "refund_type":      None,
            "estimated_amount": 0.0,
            "order_total":      None,
            "policy_note":      (
                f"'{reason}' is not a recognised reason. Valid reasons: "
                + ", ".join(sorted(VALID_REASONS))
            ),
        }

    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select(
                "id,order_number,status,subtotal,delivery_fee,service_fee,"
                "tip,total,placed_at,estimated_delivery_at,delivered_at,customer_id"
            )
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {
            "eligible":         False,
            "reason":           reason,
            "refund_type":      None,
            "estimated_amount": 0.0,
            "order_total":      None,
            "policy_note":      "Order not found.",
        }

    o = resp.data[0]
    status = o["status"]

    # Status gate
    if status in ("pending", "out_for_delivery"):
        return {
            "eligible":         False,
            "reason":           reason,
            "refund_type":      None,
            "estimated_amount": 0.0,
            "order_total":      float(o["total"]),
            "policy_note":      (
                f"Order is currently '{status}'. Refunds can only be processed "
                "after delivery or cancellation."
            ),
        }

    # 24-hour window for delivered orders
    if status == "delivered":
        placed_dt = _parse_dt(o["placed_at"])
        if placed_dt and (_now() - placed_dt) > timedelta(hours=24):
            return {
                "eligible":         False,
                "reason":           reason,
                "refund_type":      None,
                "estimated_amount": 0.0,
                "order_total":      float(o["total"]),
                "policy_note":      "Refund window expired. Refunds must be requested within 24 hours of delivery.",
            }

    # Reason-specific logic
    total        = float(o["total"])
    delivery_fee = float(o["delivery_fee"])
    service_fee  = float(o["service_fee"])

    if reason == "late_delivery":
        # Measure actual lateness
        delivered_dt    = _parse_dt(o.get("delivered_at"))
        est_delivery_dt = _parse_dt(o.get("estimated_delivery_at"))
        minutes_late    = _minutes_between(est_delivery_dt, delivered_dt) or 0.0

        if minutes_late <= 30:
            return {
                "eligible":         False,
                "reason":           reason,
                "refund_type":      "partial",
                "estimated_amount": 0.0,
                "order_total":      total,
                "policy_note":      (
                    f"Order was {minutes_late:.0f} min late. Partial refund (delivery + service fee) "
                    "is only available when delay exceeds 30 minutes."
                ),
            }
        amount = round(delivery_fee + service_fee, 2)
        return {
            "eligible":         True,
            "reason":           reason,
            "refund_type":      "partial",
            "estimated_amount": amount,
            "order_total":      total,
            "policy_note":      (
                f"Order was {minutes_late:.0f} min late. Eligible for a partial refund "
                f"of ${amount:.2f} (delivery fee + service fee)."
            ),
        }

    # All other eligible reasons → full refund
    if reason in ("missing_items", "wrong_items", "food_quality",
                  "order_not_arrived", "restaurant_cancelled"):
        return {
            "eligible":         True,
            "reason":           reason,
            "refund_type":      "full",
            "estimated_amount": total,
            "order_total":      total,
            "policy_note":      f"Eligible for a full refund of ${total:.2f}.",
        }

    # Fallback (should not reach here)
    return {
        "eligible":         False,
        "reason":           reason,
        "refund_type":      None,
        "estimated_amount": 0.0,
        "order_total":      total,
        "policy_note":      "Unable to determine eligibility.",
    }

# ── 5. issue_refund ────────────────────────────────────────────────────────────

async def issue_refund(
    order_number: str,
    reason: str,
    refund_type: str,
    amount: float,
) -> dict:
    """
    Inserts an approved refund and a resolved support ticket.
    If refund_type == 'credits', adds the amount to the customer's credit balance.
    """
    import uuid

    # Fetch order
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select("id,customer_id,total")
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"success": False, "message": "Order not found."}

    order     = resp.data[0]
    order_id  = order["id"]
    cust_id   = order["customer_id"]
    now_str   = _now().isoformat()
    refund_id = str(uuid.uuid4())

    # Insert refund
    await asyncio.to_thread(
        lambda: supabase.table("lupi_refunds").insert({
            "id":           refund_id,
            "order_id":     order_id,
            "customer_id":  cust_id,
            "amount":       round(amount, 2),
            "type":         refund_type,
            "reason":       reason,
            "status":       "approved",
            "issued_by":    "lupi_agent",
            "created_at":   now_str,
            "processed_at": now_str,
        }).execute()
    )

    # Insert resolved support ticket
    ticket_id = str(uuid.uuid4())
    await asyncio.to_thread(
        lambda: supabase.table("lupi_support_tickets").insert({
            "id":          ticket_id,
            "order_id":    order_id,
            "customer_id": cust_id,
            "issue_type":  reason,
            "status":      "resolved",
            "resolution":  "refund_issued",
            "refund_id":   refund_id,
            "created_at":  now_str,
            "resolved_at": now_str,
        }).execute()
    )

    # Credit balance update
    if refund_type == "credits":
        cust_resp = await asyncio.to_thread(
            lambda: supabase.table("lupi_customers")
                .select("credits_balance")
                .eq("id", cust_id)
                .limit(1)
                .execute()
        )
        if cust_resp.data:
            current = float(cust_resp.data[0]["credits_balance"] or 0)
            await asyncio.to_thread(
                lambda: supabase.table("lupi_customers")
                    .update({"credits_balance": round(current + amount, 2)})
                    .eq("id", cust_id)
                    .execute()
            )

    processing_note = (
        "Instant — credits added to your account."
        if refund_type == "credits"
        else "3-5 business days for card refunds, instant for credits"
    )

    return {
        "success":               True,
        "refund_id":             refund_id,
        "amount":                round(amount, 2),
        "refund_type":           refund_type,
        "estimated_processing":  processing_note,
        "message": (
            f"Refund of ${amount:.2f} has been approved and will be processed. "
            f"{processing_note}."
        ),
    }

# ── 6. create_support_ticket ───────────────────────────────────────────────────

async def create_support_ticket(
    order_number: str,
    issue_type: str,
    notes: str,
) -> dict:
    """
    Opens a support ticket for an order and records the first message from the agent.
    """
    import uuid

    # Fetch order
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select("id,customer_id")
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"success": False, "message": "Order not found."}

    order    = resp.data[0]
    order_id = order["id"]
    cust_id  = order["customer_id"]
    now_str  = _now().isoformat()
    ticket_id = str(uuid.uuid4())

    await asyncio.to_thread(
        lambda: supabase.table("lupi_support_tickets").insert({
            "id":          ticket_id,
            "order_id":    order_id,
            "customer_id": cust_id,
            "issue_type":  issue_type,
            "status":      "open",
            "created_at":  now_str,
        }).execute()
    )

    # First message from agent
    await asyncio.to_thread(
        lambda: supabase.table("lupi_ticket_messages").insert({
            "id":         str(uuid.uuid4()),
            "ticket_id":  ticket_id,
            "sender":     "lupi_agent",
            "message":    notes,
            "created_at": now_str,
        }).execute()
    )

    return {
        "success":    True,
        "ticket_id":  ticket_id,
        "issue_type": issue_type,
        "status":     "open",
        "message": (
            f"Support ticket created (ID: {ticket_id[:8]}…). "
            "Our team will review it and follow up via email within 24 hours."
        ),
    }

# ── 7. get_dasher_location ─────────────────────────────────────────────────────

async def get_dasher_location(order_number: str) -> dict:
    """
    Returns the most recent delivery tracking event for the order.
    Estimates minutes remaining based on event type if possible.
    """
    # Resolve order → dasher
    resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_orders")
            .select("id,dasher_id,estimated_delivery_at,status")
            .eq("order_number", order_number)
            .limit(1)
            .execute()
    )
    if not resp.data:
        return {"error": "order_not_found"}

    order    = resp.data[0]
    order_id = order["id"]

    # Dasher name
    dasher_name = None
    if order.get("dasher_id"):
        d = await asyncio.to_thread(
            lambda: supabase.table("lupi_dashers")
                .select("first_name")
                .eq("id", order["dasher_id"])
                .limit(1)
                .execute()
        )
        if d.data:
            dasher_name = d.data[0]["first_name"]

    # Latest tracking event
    track_resp = await asyncio.to_thread(
        lambda: supabase.table("lupi_delivery_tracking")
            .select("event,lat,lng,note,recorded_at")
            .eq("order_id", order_id)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
    )

    if not track_resp.data:
        # Estimate from order timestamps instead
        est_dt = _parse_dt(order.get("estimated_delivery_at"))
        mins_remaining = None
        if est_dt:
            diff = _minutes_between(_now(), est_dt)
            mins_remaining = max(0.0, diff) if diff is not None else None

        return {
            "status":  "no_tracking_data",
            "message": "Dasher location not available — GPS tracking not yet started.",
            "dasher_name":              dasher_name,
            "estimated_minutes_remaining": mins_remaining,
        }

    row = track_resp.data[0]
    event        = row["event"]
    recorded_at  = row["recorded_at"]

    # Estimate remaining delivery time from estimated_delivery_at
    est_dt = _parse_dt(order.get("estimated_delivery_at"))
    mins_remaining = None
    if est_dt:
        diff = _minutes_between(_now(), est_dt)
        mins_remaining = max(0.0, diff) if diff is not None else None

    return {
        "dasher_name":               dasher_name,
        "last_event":                event,
        "last_event_time":           recorded_at,
        "lat":                       row.get("lat"),
        "lng":                       row.get("lng"),
        "note":                      row.get("note"),
        "estimated_minutes_remaining": mins_remaining,
    }
