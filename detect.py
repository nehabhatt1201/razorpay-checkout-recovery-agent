"""
detect.py
Stage 1 of the pipeline: DETECT
"""

import json

DATA_PATH = "data/synthetic_orders.json"
MAX_CONTACT_ATTEMPTS = 2


def load_orders(path=DATA_PATH):
    with open(path, "r") as f:
        return json.load(f)


def classify_event_type(order):
    et = order.get("event_type")
    if et == "order.paid":
        return "order_paid"
    if et == "payment.failed":
        return "payment_failed"
    if et == "checkout_abandoned":
        return "checkout_abandoned"
    return "unknown"


def is_excluded(order):
    if order.get("opted_out"):
        return True, "customer_opted_out"
    if order.get("already_contacted_count", 0) >= MAX_CONTACT_ATTEMPTS:
        return True, "max_contact_attempts_reached"
    return False, None


def detect_events(path=DATA_PATH):
    orders = load_orders(path)
    events = []
    for order in orders:
        bucket = classify_event_type(order)
        excluded, reason = is_excluded(order)
        event = dict(order)
        event["bucket"] = bucket
        event["excluded"] = excluded
        event["exclusion_reason"] = reason
        events.append(event)
    return events


def summarize(events):
    summary = {"order_paid": 0, "payment_failed": 0, "checkout_abandoned": 0, "unknown": 0}
    excluded_count = 0
    for e in events:
        summary[e["bucket"]] = summary.get(e["bucket"], 0) + 1
        if e["excluded"]:
            excluded_count += 1
    return summary, excluded_count


if __name__ == "__main__":
    events = detect_events()
    summary, excluded_count = summarize(events)
    print(f"Total events loaded: {len(events)}")
    print(f"  order_paid:          {summary['order_paid']}")
    print(f"  payment_failed:      {summary['payment_failed']}")
    print(f"  checkout_abandoned:  {summary['checkout_abandoned']}")
    print(f"  unknown:             {summary['unknown']}")
    print(f"Excluded from further processing (opted out / max-contacted): {excluded_count}")
    eligible = [e for e in events if not e["excluded"] and e["bucket"] in ("payment_failed", "checkout_abandoned")]
    print(f"Eligible for diagnosis in next stage: {len(eligible)}")