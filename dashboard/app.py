"""
dashboard/app.py
Streamlit dashboard -- the visual you'll actually show in your 5-minute
pitch video. Runs the full pipeline live and displays the funnel.

Run with: streamlit run dashboard/app.py
(run this from the recovery-agent root folder, not from inside dashboard/)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from track import run_pipeline, compute_metrics

st.set_page_config(page_title="Checkout Recovery Agent", layout="wide")

st.title("Checkout Drop-off & Payment Failure Recovery Agent")
st.caption("Razorpay AI Buildathon — Track 3: AI Revenue Recovery")

with st.spinner("Running pipeline: detect -> diagnose -> decide -> act ..."):
    events, diagnosed, decisions, actions, events_by_id = run_pipeline()
    metrics, conversions = compute_metrics(events, diagnosed, decisions, actions, events_by_id)

# ---- Top-line funnel metrics ----
st.subheader("Funnel")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total events", metrics["total_events"])
col2.metric("Excluded upfront", metrics["excluded_upfront"])
col3.metric("Diagnosed", metrics["diagnosed"])
col4.metric("Recoverable", metrics["recoverable_diagnosed"])
col5.metric("Actions taken", metrics["actions_taken"])

st.divider()

# ---- Simulated outcome section, clearly labeled ----
st.subheader("Simulated recovery outcome")
st.warning(
    "These numbers are SIMULATED on synthetic test-mode data using a "
    "per-bucket response-probability model — they illustrate what the "
    "pipeline *would* measure with real customer responses, not a "
    "real-world guarantee."
)
c1, c2, c3 = st.columns(3)
c1.metric("Simulated recovery rate", f"{metrics['simulated_recovery_rate_pct']}%")
c2.metric("Simulated recovered value", f"₹{metrics['simulated_recovered_value_inr']:,}")
c3.metric("Total value in play", f"₹{metrics['total_value_in_play_inr']:,}")

st.divider()

# ---- Diagnosis breakdown ----
st.subheader("Diagnosis breakdown")
bucket_counts = {}
for d in diagnosed:
    bucket_counts[d["diagnosis_bucket"]] = bucket_counts.get(d["diagnosis_bucket"], 0) + 1
df_buckets = pd.DataFrame(list(bucket_counts.items()), columns=["Diagnosis bucket", "Count"]).sort_values("Count", ascending=False)
st.bar_chart(df_buckets.set_index("Diagnosis bucket"))

st.divider()

# ---- Action breakdown ----
st.subheader("Actions taken")
action_counts = {}
for d in decisions:
    action_counts[d["action"]] = action_counts.get(d["action"], 0) + 1
df_actions = pd.DataFrame(list(action_counts.items()), columns=["Action", "Count"]).sort_values("Count", ascending=False)
st.bar_chart(df_actions.set_index("Action"))

st.divider()

# ---- Correctly suppressed cases (the honesty section) ----
st.subheader("Correctly suppressed cases (no_action, with reason)")
st.caption("These prove the agent doesn't spam everyone — it explicitly withholds action when confidence is low or the case isn't recoverable.")
suppressed = [d for d in decisions if d["action"] == "no_action"][:8]
for s in suppressed:
    st.text(f"[{s['order_id']}] {s['reason']}")

st.divider()

# ---- Sample messages sent ----
st.subheader("Sample recovery messages (mock-sent)")
for a in actions[:5]:
    with st.container(border=True):
        st.markdown(f"**{a['order_id']}** — `{a['action']}`")
        st.write(a["message"])

st.divider()

# ---- Full audit log ----
st.subheader("Full audit trail")
st.caption("Every decision the agent made, with its reason — nothing here is a black box.")
df_decisions = pd.DataFrame(decisions)
st.dataframe(df_decisions[["order_id", "diagnosis_bucket", "confidence", "action", "reason"]], use_container_width=True)