# Checkout Drop-off & Payment Failure Recovery Agent

**Razorpay AI Buildathon — Track 3: AI Revenue Recovery**

## The problem

Checkout abandonment and payment failure are among the biggest silent revenue leaks in online payments. A large share of failures are not genuine declines — they're temporary technical issues (bank timeouts, OTP delays, gateway errors) that block a customer who actually wanted to complete the purchase. Every one of these is a transaction Razorpay, the merchant, and the customer all lose — with no equivalent "walk into a store and pay cash" fallback, since this is an online transaction.

The hard part isn't sending a reminder. It's telling apart the customer who hit a fixable technical snag from the one who genuinely changed their mind — and only acting on the first group, so the system helps rather than spams.

## What this agent does

This agent watches failed and abandoned checkout events, diagnoses *why* each one happened, decides — through an explicit, readable rules engine — whether it's worth acting on, drafts a tailored recovery message only for the cases that clear that bar, and logs every decision with its reason.

**Pipeline:** `Detect → Diagnose → Decide → Act → Track`

## Architecture

See [architecture.md](architecture.md) for the full diagram and stage-by-stage breakdown.

## Results (synthetic test batch, 78 orders)

| Metric | Value |
|---|---|
| Total events processed | 78 |
| Excluded upfront (opted-out / max-contacted) | 6 |
| Diagnosed | 54 |
| Diagnosed as recoverable | 40 |
| Diagnosed as not recoverable | 14 |
| Actions taken (nudges sent) | 37 |
| Correctly suppressed (no_action, with reason) | 17 |
| Simulated recovery rate* | 54.1% |
| Simulated recovered value (INR)* | ₹96,591 |
| Total order value in play (INR) | ₹2,96,885 |

\* *Simulated* using a per-diagnosis-bucket response-probability model on synthetic data — this illustrates what the pipeline would measure with real customer responses. It is not a real-world recovery guarantee, and is labeled as such everywhere it's shown, including in the dashboard.

## How it's bounded, explainable, and safe

- **Never auto-charges or auto-retries payment.** The agent only sends a message with a link back to a pre-filled checkout — the customer must act themselves.
- **Never invents discounts or incentives.** The message-drafting prompt explicitly forbids this.
- **Hard gates before any action:** a confidence threshold, a minimum order-value floor, an opt-out check, and a max-contact-attempts cap — all enforced in plain, readable rules in `decide.py`, not a black box.
- **Every decision is logged with a reason** — see `data/audit_log.json` for the full trail. Nothing here is undocumented.
- **Graceful degradation:** if the LLM call fails or no API credit is available, the pipeline automatically falls back to deterministic rule-based logic rather than breaking — see the fallback paths in `diagnose.py` and `act.py`.
- **Explicit suppression, not silent dropping:** cases like `user_cancelled` and `low_intent_abandonment` are deliberately mapped to `no_action` with a stated reason, so the system never nudges someone who plainly wasn't interested.

## Why this is complementary to Razorpay's existing infrastructure

Smart routing and retry logic work *during* a transaction, at the payment-infra layer, to prevent failures before they happen. This agent works *after* a failure or abandonment, at the customer-communication and intent-diagnosis layer, to recover the remainder through targeted, consented outreach. The two are not competing — one prevents, the other recovers what still gets through.

## What I'd build next with more time

- Real Razorpay test-mode webhook integration in place of the synthetic dataset
- A real SMS/WhatsApp send integration (currently mock-sent and logged)
- A/B testing different message phrasing per diagnosis bucket
- Extending the same detect→diagnose→decide→act→track architecture to B2B receivables and failed-subscription recovery

## Setup / how to run

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd recovery-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your API keys to a .env file (see .env.example)
ANTHROPIC_API_KEY=your_key_here
RAZORPAY_KEY_ID=your_key_here
RAZORPAY_KEY_SECRET=your_key_here

# 4. Generate the synthetic dataset
python generate_data.py

# 5. Run each pipeline stage individually (optional, for inspection)
python detect.py
python diagnose.py
python decide.py
python act.py
python track.py

# 6. Launch the full dashboard
python -m streamlit run dashboard/app.py
```

## Project structure

```
recovery-agent/
├── README.md
├── architecture.md
├── requirements.txt
├── .env.example
├── .gitignore
├── generate_data.py       # builds the synthetic test dataset
├── detect.py              # stage 1: event classification + exclusion filters
├── diagnose.py            # stage 2: rule-based + LLM diagnosis
├── decide.py              # stage 3: gated policy engine + audit logging
├── act.py                 # stage 4: message drafting + mock-send
├── track.py               # stage 5: funnel metrics
├── data/
│   ├── synthetic_orders.json
│   ├── audit_log.json
│   ├── action_log.json
│   └── metrics.json
└── dashboard/
    └── app.py             # Streamlit dashboard
```