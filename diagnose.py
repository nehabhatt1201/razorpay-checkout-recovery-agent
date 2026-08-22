"""
diagnose.py
Stage 2 of the pipeline: DIAGNOSE

Takes the eligible events from detect.py and figures out WHY each one
happened, and how confident we are that it's a recoverable case (as
opposed to a genuine decline / not-interested customer).

Two diagnosis paths, on purpose:
  1. payment_failed events HAVE an error_code from Razorpay -> we can
     deterministically bucket these with simple rules. No LLM needed,
     no ambiguity to resolve.
  2. checkout_abandoned events have NO error_code -> genuinely ambiguous,
     so we use the Claude API to reason over behavioral signals and
     produce a confidence score + a short human-readable justification.
     This justification is what goes into the audit trail.

Every diagnosis output includes a "reason" string -- this is not
optional flavour text, it is the audit trail the buildathon judging
criteria explicitly asks for.

Run directly with: python diagnose.py
"""

import os
import json
from dotenv import load_dotenv
from detect import detect_events

load_dotenv()

# ---- Rule-based bucketing for payment_failed events -----------------------

TECHNICAL_ERROR_CODES = {"GATEWAY_ERROR", "SERVER_ERROR"}

AUTH_KEYWORDS = ["otp", "3d secure", "authentication"]
BALANCE_KEYWORDS = ["insufficient balance", "declined by issuing bank", "transaction limit"]
USER_CANCELLED_KEYWORDS = ["cancelled by user"]


def diagnose_payment_failure(event):
    code = (event.get("error_code") or "").upper()
    desc = (event.get("error_description") or "").lower()

    if code in TECHNICAL_ERROR_CODES:
        return {
            "diagnosis_bucket": "technical_failure",
            "confidence": 0.9,
            "reason": f"error_code={code} is a known infra/gateway failure ('{desc}') — not a customer decision.",
        }

    if any(k in desc for k in AUTH_KEYWORDS):
        return {
            "diagnosis_bucket": "auth_friction",
            "confidence": 0.85,
            "reason": f"Failure description matches auth/OTP friction pattern ('{desc}').",
        }

    if any(k in desc for k in BALANCE_KEYWORDS):
        return {
            "diagnosis_bucket": "payment_method_issue",
            "confidence": 0.6,
            "reason": f"Failure description matches payment-method issue ('{desc}') — recoverable if alt. method offered.",
        }

    if any(k in desc for k in USER_CANCELLED_KEYWORDS):
        return {
            "diagnosis_bucket": "user_cancelled",
            "confidence": 0.15,
            "reason": f"Customer actively cancelled mid-flow ('{desc}') — low recovery likelihood, treat as low intent.",
        }

    return {
        "diagnosis_bucket": "unclassified_failure",
        "confidence": 0.3,
        "reason": f"error_code={code}, description='{desc}' did not match a known bucket — treat cautiously.",
    }


# ---- LLM-based intent scoring for checkout_abandoned events ---------------

def diagnose_abandonment_rule_fallback(event):
    """
    A deterministic fallback used if no Claude API key / call fails,
    so the pipeline never silently breaks in a demo. Same logic shape
    as what we ask the LLM to reason about, just simpler.
    """
    stage = event.get("checkout_stage_reached", "")
    time_on_page = event.get("time_on_checkout_seconds", 0)
    returning = event.get("returning_customer", False)

    if stage in ("payment_page_viewed", "payment_method_selected") and time_on_page > 60:
        confidence = 0.75 if returning else 0.6
        return {
            "diagnosis_bucket": "high_intent_abandonment",
            "confidence": confidence,
            "reason": (
                f"Reached '{stage}' and spent {time_on_page}s on checkout "
                f"({'returning' if returning else 'new'} customer) — signals genuine intent."
            ),
        }

    return {
        "diagnosis_bucket": "low_intent_abandonment",
        "confidence": 0.2,
        "reason": f"Only reached '{stage}' with {time_on_page}s on checkout — weak intent signal, likely browsing.",
    }


def diagnose_abandonment_with_llm(event, client):
    """
    Uses Claude to reason over behavioral signals for an abandoned
    checkout and return a bucket + confidence + justification.
    Falls back to the rule-based version on any API error, so the
    pipeline is never blocked by network/billing issues during a demo.
    """
    prompt = f"""You are helping classify an abandoned e-commerce checkout to decide if it's worth a recovery message.

Order details:
- Product: {event.get('product_name')}
- Amount: INR {event.get('amount_inr')}
- Checkout stage reached: {event.get('checkout_stage_reached')}
- Time spent on checkout: {event.get('time_on_checkout_seconds')} seconds
- Returning customer: {event.get('returning_customer')}

Classify this as either "high_intent_abandonment" (likely wanted to buy, got
interrupted/distracted, worth a gentle nudge) or "low_intent_abandonment"
(likely just browsing, not worth contacting).

Respond ONLY with valid JSON, no other text, in this exact format:
{{"diagnosis_bucket": "high_intent_abandonment" or "low_intent_abandonment", "confidence": 0.0 to 1.0, "reason": "one short sentence"}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # strip accidental markdown fences if the model adds them
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        # basic validation before trusting it
        assert result["diagnosis_bucket"] in ("high_intent_abandonment", "low_intent_abandonment")
        assert 0.0 <= float(result["confidence"]) <= 1.0
        return result
    except Exception as e:
        fallback = diagnose_abandonment_rule_fallback(event)
        fallback["reason"] = f"[LLM call failed ({e}), used rule-based fallback] " + fallback["reason"]
        return fallback


# ---- Orchestration ---------------------------------------------------------

def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except Exception:
        return None


def diagnose_events(events, use_llm=True):
    client = get_anthropic_client() if use_llm else None
    diagnosed = []

    for event in events:
        if event["excluded"] or event["bucket"] not in ("payment_failed", "checkout_abandoned"):
            continue  # nothing to diagnose — already filtered or not actionable

        if event["bucket"] == "payment_failed":
            diagnosis = diagnose_payment_failure(event)
        else:  # checkout_abandoned
            if client is not None:
                diagnosis = diagnose_abandonment_with_llm(event, client)
            else:
                diagnosis = diagnose_abandonment_rule_fallback(event)
                diagnosis["reason"] = "[No API key configured, used rule-based fallback] " + diagnosis["reason"]

        enriched = dict(event)
        enriched.update(diagnosis)
        diagnosed.append(enriched)

    return diagnosed


if __name__ == "__main__":
    events = detect_events()
    diagnosed = diagnose_events(events, use_llm=True)

    print(f"Diagnosed {len(diagnosed)} events\n")

    bucket_counts = {}
    for d in diagnosed:
        bucket_counts[d["diagnosis_bucket"]] = bucket_counts.get(d["diagnosis_bucket"], 0) + 1

    for bucket, count in sorted(bucket_counts.items()):
        print(f"  {bucket}: {count}")

    print("\nSample diagnoses:")
    for d in diagnosed[:5]:
        print(f"  [{d['order_id']}] bucket={d['diagnosis_bucket']} confidence={d['confidence']:.2f}")
        print(f"     reason: {d['reason']}")