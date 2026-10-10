"""FastMCP tools over the demo's JSON banking data and local audit store."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data.json"
DB_PATH = ROOT / "audit.db"
mcp = FastMCP("AML Mock Banking Systems")
cases: dict[str, dict[str, Any]] = {}
pending_approvals: dict[str, dict[str, Any]] = {}
notifications: list[dict[str, Any]] = []


def _data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _audit_table() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, alert_id TEXT, action TEXT, details TEXT, timestamp TEXT)")


@mcp.tool()
def get_alert(alert_id: str) -> dict[str, Any]:
    """Fetch one mock transaction monitoring alert."""
    alert = next((x for x in _data()["alerts"] if x["alert_id"] == alert_id), None)
    if alert is None:
        raise ValueError(f"Unknown alert_id: {alert_id}")
    return alert


@mcp.tool()
def get_customer(customer_id: str) -> dict[str, Any]:
    """Fetch the customer profile associated with an alert."""
    item = next((x for x in _data()["customers"] if x["customer_id"] == customer_id), None)
    if item is None:
        raise ValueError(f"Unknown customer_id: {customer_id}")
    return item


@mcp.tool()
def get_transactions(customer_id: str) -> list[dict[str, Any]]:
    """Fetch all mock transactions for a customer."""
    return [x for x in _data()["transactions"] if x["customer_id"] == customer_id]


@mcp.tool()
def screen_entity(name: str, country: str) -> dict[str, Any]:
    """Screen a counterparty name and country against the small demo lists."""
    lists = _data()["screening"]
    sanctions_hit = any(country.casefold() == x.casefold() for x in lists["sanctioned_countries"])
    pep_hit = any(name.casefold() == x.casefold() for x in lists["pep_names"])
    adverse_hit = any(term.casefold() in name.casefold() for term in lists["adverse_media_terms"])
    match_score = 92 if pep_hit else (100 if sanctions_hit else (65 if adverse_hit else 0))
    return {"name": name, "country": country, "sanctions_hit": sanctions_hit, "pep_hit": pep_hit,
            "adverse_media_hit": adverse_hit, "match_score": match_score}


@mcp.tool()
def create_case(alert_id: str, risk_score: int, summary: str) -> dict[str, Any]:
    """Create an analyst case in the in-memory case store."""
    case = {"case_id": f"CASE-{alert_id}", "alert_id": alert_id, "risk_score": risk_score,
            "summary": summary, "status": "open", "created_at": datetime.now().isoformat()}
    cases[alert_id] = case
    return case


@mcp.tool()
def file_sar(alert_id: str, narrative: str) -> dict[str, Any]:
    """Record a mock SAR filing after human approval."""
    result = {"sar_id": f"SAR-{alert_id}", "alert_id": alert_id, "status": "filed", "narrative": narrative,
              "filed_at": datetime.now().isoformat()}
    cases.setdefault(alert_id, {"alert_id": alert_id, "status": "open"})["sar"] = result
    return result


@mcp.tool()
def log_audit(alert_id: str, action: str, details: str) -> dict[str, Any]:
    """Write an audit event to both SQLite and the in-memory response."""
    _audit_table()
    stamp = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("INSERT INTO audit_log (alert_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
                           (alert_id, action, details, stamp))
        event_id = cur.lastrowid
    return {"audit_id": event_id, "alert_id": alert_id, "action": action, "details": details, "timestamp": stamp}


@mcp.tool()
def notify_analyst(message: str) -> dict[str, Any]:
    """Add a message to the local mock analyst notification queue."""
    notice = {"message": message, "created_at": datetime.now().isoformat()}
    notifications.append(notice)
    return notice


@mcp.tool()
def set_pending_approval(alert_id: str, recommendation: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Pause a high-risk alert for explicit analyst approval."""
    pending = {"alert_id": alert_id, "recommendation": recommendation, "evidence": evidence,
               "status": "pending", "created_at": datetime.now().isoformat()}
    pending_approvals[alert_id] = pending
    return pending


@mcp.tool()
def approve_action(alert_id: str) -> dict[str, Any]:
    """Mark a pending recommendation approved by a human."""
    pending = pending_approvals.get(alert_id)
    if not pending or pending["status"] != "pending":
        raise ValueError(f"No pending approval for {alert_id}")
    pending["status"] = "approved"
    pending["approved_at"] = datetime.now().isoformat()
    return pending


@mcp.tool()
def reject_action(alert_id: str, reason: str = "Rejected by analyst") -> dict[str, Any]:
    """Record a human rejection of a pending recommendation."""
    pending = pending_approvals.get(alert_id)
    if not pending or pending["status"] != "pending":
        raise ValueError(f"No pending approval for {alert_id}")
    pending["status"] = "rejected"
    pending["reason"] = reason
    pending["rejected_at"] = datetime.now().isoformat()
    return pending


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
