# Architecture

## Pipeline overview

```
 Razorpay Webhooks / Events
 (payment.failed, order.paid, checkout_abandoned)
              │
              ▼
        ┌───────────┐
        │  DETECT   │  detect.py
        └───────────┘
              │  classifies event type
              │  applies hard exclusion filters
              │  (opted-out, max-contacted)
              ▼
        ┌───────────┐
        │ DIAGNOSE  │  diagnose.py
        └───────────┘
              │  payment_failed  -> rule-based bucket
              │                    (error_code / description)
              │  abandonment     -> LLM intent scoring
              │                    (falls back to rules if
              │                     API unavailable)
              ▼
        ┌───────────┐
        │  DECIDE   │  decide.py
        └───────────┘
              │  confidence gate
              │  order-value gate
              │  policy-mapped no_action buckets
              │  -> logs every decision + reason
              ▼
        ┌───────────┐
        │    ACT    │  act.py
        └───────────┘
              │  drafts tailored message (LLM or template)
              │  mock-sends (logs, no real gateway)
              │  never auto-charges / auto-retries
              ▼
        ┌───────────┐
        │   TRACK   │  track.py + dashboard/app.py
        └───────────┘
              │  funnel metrics, simulated recovery rate,
              │  suppressed-case examples, full audit trail
              ▼
        Streamlit Dashboard (pitch demo)
```

## Stage-by-stage detail

### 1. Detect (`detect.py`)
Reads raw order/payment events (in production: Razorpay webhooks `payment.failed` and `order.paid`, plus a timeout check for abandonment when `order.paid` never fires). Classifies each into `order_paid`, `payment_failed`, or `checkout_abandoned`.

**Why it's safe:** two hard exclusion filters run here, before anything reaches diagnosis — `opted_out` customers and orders that have already hit the max-contact cap are removed immediately. This is defense-in-depth: even if a later stage has a bug, these customers are never contacted.

### 2. Diagnose (`diagnose.py`)
Two distinct paths, deliberately:
- **Payment failures** carry a Razorpay `error_code`, so we use deterministic rule-based bucketing (technical failure, auth friction, payment-method issue, user-cancelled). No ambiguity, no LLM needed.
- **Abandonments** carry no error code, so the reason is genuinely uncertain. We use the Claude API to reason over behavioral signals (checkout stage reached, time on page, returning-customer status) and produce a bucket, a confidence score, and a one-line justification.

**Why it's safe:** if the LLM call fails for any reason (network, billing, malformed response), the code automatically falls back to a simpler rule-based version rather than crashing or guessing silently. This means a live demo never breaks because of an external API hiccup.

### 3. Decide (`decide.py`)
The explicit, readable policy layer. Every decision passes through, in order:
1. A confidence floor (below threshold → no action, too uncertain)
2. An order-value floor (below minimum → not worth recovery effort)
3. A policy map from diagnosis bucket to action — some buckets (`user_cancelled`, `low_intent_abandonment`) are *deliberately* mapped to `no_action`, not defaulted there by omission

Every single decision — including "no action" ones — is written to `data/audit_log.json` with a plain-English reason. This is the audit trail.

### 4. Act (`act.py`)
For every decision that passed the gates, drafts a specific message (via Claude, with a template fallback) matched to the diagnosis — a technical failure gets "nothing's wrong with your card, please retry," not the same generic message as an OTP issue.

**Trust boundaries enforced here:**
- The agent only ever sends a link back to checkout. It never auto-charges or auto-retries a payment on the customer's behalf — the customer must act.
- The message-drafting prompt explicitly forbids inventing discounts or incentives.
- Mock-sending is logged, not actually delivered — no real SMS/WhatsApp gateway is wired up for this build, since the judging bar is about the decision logic, not the delivery integration.

### 5. Track (`track.py` + `dashboard/app.py`)
Computes the full funnel: total events, how many were excluded, diagnosed, judged recoverable vs not, and acted on. Includes a clearly-labeled **simulated** recovery rate (since real customer response data doesn't exist in test mode) and surfaces concrete examples of correctly suppressed cases — proof the system isn't just messaging everyone.

## Why this is complementary to Razorpay's existing systems

Razorpay's smart routing and retry infrastructure work *during* a transaction, at the payment-infra layer, to prevent failures before they happen. This agent works *after* a failure or abandonment already occurred, at the customer-communication and intent-diagnosis layer, to recover what still got through. The two layers are complementary, not competing.

## Honesty and scope notes

- All data in this build is **synthetic**, generated by `generate_data.py` with deliberately varied categories (successes, four types of failure, two intent levels of abandonment, and edge cases like opted-out customers and already-maxed-out contact counts).
- The "recovery rate" shown is a **simulation**, not a claim about real-world performance — it uses a per-bucket response-probability model to illustrate what the pipeline's output would look like with real customer responses.
- No real payment gateway, SMS/WhatsApp provider, or live Razorpay account is integrated in this build — the architecture is designed so those integrations are a drop-in replacement for the mocked pieces, not a redesign.