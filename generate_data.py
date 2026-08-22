"""
generate_data.py
Generates data/synthetic_orders.json — the fake test dataset the whole
recovery agent pipeline runs on.

Run this once with: python generate_data.py
"""

import json
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible dataset

CUSTOMERS = [f"cust_{i:04d}" for i in range(1, 71)]
PRODUCTS = [
    ("Laptop - 15 inch", 55000),
    ("Wireless Earbuds", 2499),
    ("Smartwatch", 6999),
    ("Office Chair", 8500),
    ("Bluetooth Speaker", 1899),
    ("4K Monitor", 18500),
    ("Mechanical Keyboard", 4200),
    ("Running Shoes", 3200),
    ("Backpack", 1599),
    ("Air Fryer", 5400),
]

now = datetime(2026, 8, 20, 10, 0, 0)


def rand_time_before(hours_back_max):
    return (now - timedelta(hours=random.uniform(0.5, hours_back_max))).isoformat()


def make_order(order_id, category):
    product, price = random.choice(PRODUCTS)
    customer = random.choice(CUSTOMERS)
    base = {
        "order_id": f"order_{order_id:04d}",
        "customer_id": customer,
        "product_name": product,
        "amount_inr": price,
        "created_at": rand_time_before(72),
    }

    if category == "success":
        base.update({
            "event_type": "order.paid",
            "error_code": None,
            "error_description": None,
            "checkout_stage_reached": "payment_completed",
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "failed_technical":
        base.update({
            "event_type": "payment.failed",
            "error_code": random.choice(["GATEWAY_ERROR", "SERVER_ERROR"]),
            "error_description": random.choice([
                "issue in payment gateway, please retry",
                "bank server timeout during transaction",
                "network error while processing payment",
            ]),
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "failed_auth":
        base.update({
            "event_type": "payment.failed",
            "error_code": "BAD_REQUEST_ERROR",
            "error_description": random.choice([
                "otp not received by customer",
                "otp entered was incorrect",
                "3D secure authentication failed / timed out",
            ]),
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "failed_balance":
        base.update({
            "event_type": "payment.failed",
            "error_code": "BAD_REQUEST_ERROR",
            "error_description": random.choice([
                "insufficient balance in account",
                "card declined by issuing bank",
                "transaction limit exceeded",
            ]),
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "failed_user_cancelled":
        base.update({
            "event_type": "payment.failed",
            "error_code": "BAD_REQUEST_ERROR",
            "error_description": "payment cancelled by user",
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "abandoned_high_intent":
        base.update({
            "event_type": "checkout_abandoned",
            "error_code": None,
            "error_description": None,
            "checkout_stage_reached": random.choice(["payment_page_viewed", "payment_method_selected"]),
            "time_on_checkout_seconds": random.randint(90, 400),
            "returning_customer": random.choice([True, False]),
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "abandoned_low_intent":
        base.update({
            "event_type": "checkout_abandoned",
            "error_code": None,
            "error_description": None,
            "checkout_stage_reached": "cart_viewed",
            "time_on_checkout_seconds": random.randint(5, 40),
            "returning_customer": False,
            "already_contacted_count": 0,
            "opted_out": False,
        })

    elif category == "edge_opted_out":
        base.update({
            "event_type": "payment.failed",
            "error_code": "GATEWAY_ERROR",
            "error_description": "issue in payment gateway, please retry",
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 0,
            "opted_out": True,  # must NOT be contacted
        })

    elif category == "edge_already_contacted_twice":
        base.update({
            "event_type": "payment.failed",
            "error_code": "GATEWAY_ERROR",
            "error_description": "bank server timeout during transaction",
            "checkout_stage_reached": "payment_attempted",
            "already_contacted_count": 2,  # hit the max-contact cap
            "opted_out": False,
        })

    elif category == "edge_low_value":
        base["amount_inr"] = 149  # below minimum recovery-effort threshold
        base.update({
            "event_type": "checkout_abandoned",
            "error_code": None,
            "error_description": None,
            "checkout_stage_reached": "payment_page_viewed",
            "time_on_checkout_seconds": 120,
            "returning_customer": False,
            "already_contacted_count": 0,
            "opted_out": False,
        })

    return base


def main():
    orders = []
    oid = 1

    def add(n, category):
        nonlocal oid
        for _ in range(n):
            orders.append(make_order(oid, category))
            oid += 1

    add(18, "success")
    add(12, "failed_technical")
    add(8, "failed_auth")
    add(7, "failed_balance")
    add(6, "failed_user_cancelled")
    add(10, "abandoned_high_intent")
    add(8, "abandoned_low_intent")
    add(3, "edge_opted_out")
    add(3, "edge_already_contacted_twice")
    add(3, "edge_low_value")

    random.shuffle(orders)

    with open("data/synthetic_orders.json", "w") as f:
        json.dump(orders, f, indent=2)

    print(f"Generated {len(orders)} synthetic orders -> data/synthetic_orders.json")


if __name__ == "__main__":
    main()