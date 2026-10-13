"""Deterministic order and refund tools for ResolveAI Sprint 1."""

from database import connect, initialize_database


def get_order(order_id):
    """Return one order as a plain dictionary, or None when it does not exist."""
    if not order_id:
        return None

    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def check_refund_eligibility(order):
    """Apply the Sprint 1 policy without AI or subjective interpretation."""
    if not order:
        return {
            "decision": "NOT_ELIGIBLE",
            "reason": "ORDER_NOT_FOUND",
            "message": "Order was not found."
        }

    if order.get("claim_type") == "DAMAGED":
        return {
            "decision": "NEEDS_REVIEW",
            "reason": "DAMAGED_CLAIM_UNVERIFIED",
            "message": "An unverified damaged-item claim requires human review."
        }

    if order.get("refunded"):
        return {
            "decision": "NOT_ELIGIBLE",
            "reason": "ALREADY_REFUNDED",
            "message": "This order has already been refunded."
        }

    if order["status"] == "CANCELLED" and not order["has_shipped"]:
        return {
            "decision": "ELIGIBLE",
            "reason": "CANCELLED_BEFORE_SHIPMENT",
            "message": "Cancelled before shipment; automatic refund is allowed."
        }

    if order["status"] == "LOST":
        return {
            "decision": "ELIGIBLE",
            "reason": "SYSTEM_CONFIRMED_LOST",
            "message": "The system marks this order as lost; automatic refund is allowed."
        }

    if order["status"] == "IN_TRANSIT":
        return {
            "decision": "NEEDS_REVIEW",
            "reason": "IN_TRANSIT_EXCEPTION_ONLY",
            "message": "An in-transit order cannot be auto-refunded; exceptions require human review."
        }

    if order["status"] == "CANCELLED" and order["has_shipped"]:
        return {
            "decision": "NEEDS_REVIEW",
            "reason": "CANCELLED_AFTER_SHIPMENT",
            "message": "This order was cancelled after shipment and requires human review."
        }

    return {
        "decision": "NOT_ELIGIBLE",
        "reason": "STATUS_NOT_AUTO_REFUNDABLE",
        "message": "This order status is not eligible for an automatic refund."
    }


def process_refund(order_id):
    """Simulate a refund and record the result. No payment system is contacted."""
    order = get_order(order_id)
    eligibility = check_refund_eligibility(order)

    if not order:
        return {"success": False, **eligibility}

    success = eligibility["decision"] == "ELIGIBLE"
    result = "SIMULATED_REFUND_COMPLETED" if success else eligibility["reason"]

    with connect() as connection:
        if success:
            connection.execute(
                "UPDATE orders SET refunded = 1 WHERE order_id = ?",
                (order["order_id"],),
            )
        connection.execute(
            "INSERT INTO interactions (order_id, action, result) VALUES (?, ?, ?)",
            (order["order_id"], "PROCESS_REFUND", result),
        )

    return {
        "success": success,
        "decision": eligibility["decision"],
        "reason": result,
        "message": (
            "Simulated refund completed and recorded."
            if success else eligibility["message"]
        ),
    }


initialize_database()
