"""Streamlit control room for the agentic AML demo."""
import json
import os
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
ALERTS = DATA["alerts"]

st.set_page_config(page_title="AML Agent Control Room", page_icon="🛡️", layout="wide")
st.title("🛡️ Agentic AML Transaction Monitor")
st.caption("Deterministic risk decisions · MCP tool orchestration · LLM evidence synthesis")

if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = None
if "results" not in st.session_state:
    st.session_state.results = {}
if "alert_queue_selection" not in st.session_state:
    previous_selection = st.session_state.get("selected_alert_id")
    valid_alert_ids = {alert["alert_id"] for alert in ALERTS}
    st.session_state.alert_queue_selection = (
        previous_selection if previous_selection in valid_alert_ids else ALERTS[0]["alert_id"]
    )


def get_orchestrator():
    if st.session_state.orchestrator is None:
        # Keep the initial UI render lightweight; load the MCP stack when the analyst starts an investigation.
        from mcp_client import MCPClient
        from orchestrator import AgentOrchestrator
        st.session_state.orchestrator = AgentOrchestrator(MCPClient())
    return st.session_state.orchestrator

results = st.session_state.results
with st.sidebar:
    st.subheader("Alert queue")
    statuses = {}
    for item in ALERTS:
        result = results.get(item["alert_id"])
        status = result["action_taken"].replace("_", " ").title() if result else "New"
        statuses[item["alert_id"]] = status
    alert_ids = [a["alert_id"] for a in ALERTS]
    selected_id = st.radio("Select an alert", alert_ids,
                           label_visibility="collapsed", key="alert_queue_selection")
    # Keep widget options stable across reruns; changing labels when an investigation
    # completes can cause Streamlit's radio widget to lose its selected option.
    st.caption(" · ".join(f"{alert_id}: {statuses[alert_id]}" for alert_id in alert_ids))
    st.divider()
    if os.getenv("MCP_MODE", "http").strip().lower() == "inprocess":
        st.caption("MCP server: in-process FastMCP transport")
    else:
        st.caption(f"MCP server: `{os.getenv('MCP_URL', 'http://127.0.0.1:8000/mcp')}`")

alert = next(a for a in ALERTS if a["alert_id"] == selected_id)
customer = next(c for c in DATA["customers"] if c["customer_id"] == alert["customer_id"])
transactions = [t for t in DATA["transactions"] if t["customer_id"] == customer["customer_id"]]
result = results.get(selected_id)

left, right = st.columns([1.1, 1])
with left:
    st.subheader("Selected alert")
    st.markdown(f"**{alert['alert_id']}** · {alert['trigger_reason']}")
    st.write(f"**Customer:** {customer['name']} · {customer['occupation']}")
    st.write(f"**Declared income:** ${customer['declared_income']:,.0f} / year")
    st.write(f"**Customer risk rating:** {customer['risk_rating'].title()}")
with right:
    st.subheader("Observed activity")
    st.write(f"{len(transactions)} transaction(s) · ${sum(t['amount'] for t in transactions):,.2f} total")
    st.dataframe([{ "Date/time": t["timestamp"].replace("T", " "), "Amount": f"{t['currency']} {t['amount']:,.2f}",
                    "Counterparty": t["counterparty"], "Country": t["counterparty_country"], "Channel": t["channel"]}
                  for t in transactions], hide_index=True, width="stretch")

if st.button("Investigate alert", type="primary"):
    progress = st.empty()
    progress.info("Collecting evidence through MCP and applying deterministic rules…")
    try:
        result = get_orchestrator().run(selected_id)
        results[selected_id] = result
    except Exception as exc:
        progress.empty()
        st.error(f"Investigation could not complete. Check that the MCP server is running. Details: {exc}")
    else:
        # Explicitly remove progress feedback before rerunning with the completed result.
        progress.empty()
        st.rerun()

if result:
    st.divider()
    st.subheader("Investigation outcome")
    col_score, col_autonomy, col_action = st.columns(3)
    col_score.metric("Deterministic risk score", f"{result['risk_score']} / 100")
    color = {"human-out": "🟢", "human-on": "🟡", "human-in": "🔴"}[result["autonomy_level"]]
    col_autonomy.metric("Autonomy", f"{color} {result['autonomy_level']}")
    col_action.metric("Action taken", result["action_taken"].replace("_", " ").title())
    if result["risk_reasons"]:
        st.write("**Rule hits:** " + " · ".join(result["risk_reasons"]))
    else:
        st.write("**Rule hits:** None")

    st.subheader("Astra investigation summary")
    st.text_area("Evidence-grounded summary", result["summary"], height=190, disabled=True, label_visibility="collapsed")

    if result.get("pending_approval"):
        st.warning("Pending analyst approval · recommendation: freeze review and SAR review. No external transaction is frozen by this demo.")
        approve_col, reject_col = st.columns(2)
        if approve_col.button("Approve and generate SAR narrative", type="primary", width="stretch"):
            try:
                updated = get_orchestrator().approve(selected_id)
                results[selected_id] = updated
                st.rerun()
            except Exception as exc:
                st.error(f"Approval flow failed: {exc}")
        if reject_col.button("Reject recommendation", width="stretch"):
            try:
                updated = get_orchestrator().reject(selected_id)
                results[selected_id] = updated
                st.rerun()
            except Exception as exc:
                st.error(f"Rejection flow failed: {exc}")
    if result.get("sar"):
        st.success(f"SAR narrative generated after approval · {result['sar']['sar_id']}")
        st.text_area("Draft SAR narrative", result["sar"]["narrative"], height=230, disabled=True)

    st.subheader("Agent trace")
    st.caption("Each row shows an MCP tool call or the local deterministic/LLM step, with its captured input and output.")
    for entry in result["trace"]:
        with st.expander(f"{entry['step']:02d} · {entry['tool']}", expanded=False):
            st.caption(entry["timestamp"])
            st.markdown("**Input**")
            st.json(entry["input"])
            st.markdown("**Output**")
            if isinstance(entry["output"], (dict, list)):
                st.json(entry["output"])
            else:
                st.code(str(entry["output"]), language=None)
else:
    st.info("Select an alert and investigate to run the cross-system workflow. Astra is optional; without credentials the app uses a template fallback.")
