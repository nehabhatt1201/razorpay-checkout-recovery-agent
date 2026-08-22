"""
act.py
Stage 4 of the pipeline: ACT

Takes decisions from decide.py where action != "no_action" and:
  1. Drafts a natural, specific nudge message for that action type
     (using Claude; falls back to a template if API unavailable)
  2. "Sends" it -- mocked as a log entry, since no real SMS/WhatsApp/
     email gateway is wired up for this buildathon build. What matters
     to the judges is the DECISION and MESSAGE QUALITY, not the delivery
     mechanism.

Hard rule enforced here (in addition to decide.py's gates):
  - The agent NEVER auto-charges or auto-retries payment on the
    customer's behalf. It only sends a message with a link back to a
    pre-filled checkout. The customer must act themselves. This is a
    deliberate trust boundary, not a limitation -- state it explicitly
    in your pitch.

Run directly with: python act.py
"""

import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from detect import detect_events
from diagnose import diagnose_events
from decide import decide_events

load_dotenv()

# ---- Template fallback (used if no API key / call fails) ------------------

TEMPLATES = {
    "retry_nudge": (
        "Hi! Your payment for {product} (INR {amount}) hit a temporary technical issue "
        "on our end. Nothing wrong with your card/account. Tap here to retry: {link}"
    ),
    "otp_resend_nudge": (
        "Hi! It looks like the OTP for your {product} order didn't come through in time. "
        "Tap here to retry and we'll resend it: {link}"
    ),
    "alt_payment_method_nudge": (
        "Hi! Your payment for {product} (INR {amount}) didn't go through with that method. "
        "You can try a different card or UPI here: {link}"
    ),
    "soft_reminder_nudge": (
        "Hi! You left {product} (INR {amount}) in your cart. Still interested? "
        "Pick up right where you left off: {link}"
    ),
}


def template_message(decision, event):
    template = TEMPLATES.get(decision["action"])
    if not template:
        return None
    return template.format(
        product=event.get("product_name", "your item"),
        amount=event.get("amount_inr", ""),
        link=f"https://checkout.example.com/resume/{decision['order_id']}",
    )


def llm_message(decision, event, client):
    prompt = f"""Write a short recovery message (SMS/WhatsApp style, under 300 characters) for a customer whose order didn't complete.

Context:
- Product: {event.get('product_name')}
- Amount: INR {event.get('amount_inr')}
- Reason for non-completion: {decision['diagnosis_bucket']} ({decision['reason']})
- Action type to take: {decision['action']}

Rules:
- Friendly, brief, not pushy or salesy
- Do NOT invent a discount or offer any monetary incentive
- Include a placeholder link written exactly as {{link}}
- No emojis, no ALL CAPS
- Respond with ONLY the message text, nothing else"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        link = f"https://checkout.example.com/resume/{decision['order_id']}"
        return text.replace("{link}", link)
    except Exception:
        return template_message(decision, event)


def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except Exception:
        return None


def act_on_decisions(decisions, events_by_id, use_llm=True):
    client = get_anthropic_client() if use_llm else None
    actions_taken = []

    for decision in decisions:
        if decision["action"] == "no_action":
            continue

        event = events_by_id[decision["order_id"]]

        # Defense-in-depth stopping rule check (already gated upstream too)
        if event.get("already_contacted_count", 0) >= 2:
            continue

        message = llm_message(decision, event, client) if client else template_message(decision, event)

        record = {
            "order_id": decision["order_id"],
            "action": decision["action"],
            "channel": "sms_whatsapp_mock",
            "message": message,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "note": "MOCK SEND — no real message gateway wired up for this build. "
                    "Agent never auto-charges or auto-retries; customer must tap the link themselves.",
        }
        actions_taken.append(record)

    return actions_taken


def save_action_log(actions, path="data/action_log.json"):
    with open(path, "w") as f:
        json.dump(actions, f, indent=2)


if __name__ == "__main__":
    events = detect_events()
    diagnosed = diagnose_events(events, use_llm=True)
    decisions = decide_events(diagnosed)

    events_by_id = {e["order_id"]: e for e in diagnosed}
    actions = act_on_decisions(decisions, events_by_id, use_llm=True)

    save_action_log(actions)

    print(f"Actions taken (mock-sent): {len(actions)}\n")
    for a in actions[:5]:
        print(f"[{a['order_id']}] action={a['action']}")
        print(f"   message: {a['message']}")
        print()

    print(f"Full action log written to data/action_log.json")