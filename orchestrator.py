"""Deterministic AML workflow orchestration; the LLM only writes prose."""
from datetime import datetime
from typing import Any

from llm_client import generate_investigation_summary, generate_sar_narrative


class AgentOrchestrator:
    def __init__(self, mcp_client: Any, llm_client: Any = None):
        self.mcp = mcp_client
        self.llm = llm_client
        self.results: dict[str, dict[str, Any]] = {}

    def _call(self, trace: list[dict[str, Any]], tool_name: str, **inputs: Any) -> Any:
        output = self.mcp.call(tool_name, **inputs)
        trace.append({"step": len(trace) + 1, "tool": tool_name, "input": inputs, "output": output,
                      "timestamp": datetime.now().isoformat()})
        return output

    @staticmethod
    def _score(customer: dict[str, Any], transactions: list[dict[str, Any]], screenings: list[dict[str, Any]]) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        if any(float(tx.get("amount", 0)) > 100_000 for tx in transactions):
            score += 25
            reasons.append("A single transaction exceeds $100,000 (+25)")
        if any(s.get("sanctions_hit") for s in screenings):
            score += 30
            reasons.append("Counterparty is linked to a sanctioned country (+30)")
        if any(s.get("pep_hit") for s in screenings):
            score += 30
            reasons.append("Counterparty screening returned a PEP match (+30)")
        deposits = [tx for tx in transactions if tx.get("channel") == "cash_deposit" and 8_000 <= float(tx.get("amount", 0)) < 10_000]
        if len(deposits) >= 3:
            dates = [datetime.fromisoformat(tx["timestamp"]) for tx in deposits]
            if (max(dates) - min(dates)).days < 7:
                # 35 points ensures the supplied structuring example reaches human-on.
                score += 35
                reasons.append("Three or more cash deposits just under $10,000 within seven days (+35)")
        income = float(customer.get("declared_income", 0))
        activity = sum(float(tx.get("amount", 0)) for tx in transactions)
        if income > 0 and activity > 5 * income:
            score += 15
            reasons.append("Total observed activity exceeds five times declared annual income (+15)")
        return min(score, 100), reasons

    def run(self, alert_id: str) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []
        alert = self._call(trace, "get_alert", alert_id=alert_id)
        customer = self._call(trace, "get_customer", customer_id=alert["customer_id"])
        transactions = self._call(trace, "get_transactions", customer_id=customer["customer_id"])
        # Counterparty is the screened entity in these alerts; deduplicate repeated counterparties.
        screening_targets = sorted({(tx["counterparty"], tx["counterparty_country"]) for tx in transactions})
        screenings = [self._call(trace, "screen_entity", name=name, country=country) for name, country in screening_targets]
        score, reasons = self._score(customer, transactions, screenings)
        if score < 30:
            autonomy = "human-out"
            action = "auto_dismissed"
            recommendation = "Auto-dismiss under the configured low-risk threshold."
        elif score <= 70:
            autonomy = "human-on"
            action = "case_created"
            recommendation = "Create an analyst case for review."
        else:
            autonomy = "human-in"
            action = "pending_approval"
            recommendation = "Recommend transaction freeze and SAR review; human approval required."
        evidence = {
            "alert": alert,
            "customer": customer,
            "transactions": transactions,
            "screening": screenings,
            "risk_score": score,
            "risk_reasons": reasons,
            "autonomy_level": autonomy,
            "action_recommendation": recommendation,
        }
        trace.append({"step": len(trace) + 1, "tool": "rule_based_risk_score", "input": {"rules": "deterministic Python"},
                      "output": {"risk_score": score, "risk_reasons": reasons}, "timestamp": datetime.now().isoformat()})
        summary = generate_investigation_summary(evidence)
        trace.append({"step": len(trace) + 1, "tool": "Astra.generate_investigation_summary", "input": {"evidence_keys": list(evidence)},
                      "output": summary, "timestamp": datetime.now().isoformat()})
        if autonomy == "human-out":
            self._call(trace, "log_audit", alert_id=alert_id, action=action, details=f"score={score}; {recommendation}")
        elif autonomy == "human-on":
            self._call(trace, "create_case", alert_id=alert_id, risk_score=score, summary=summary)
            self._call(trace, "notify_analyst", message=f"{alert_id}: score {score}. Analyst case created.")
            self._call(trace, "log_audit", alert_id=alert_id, action=action, details=f"score={score}; {recommendation}")
        else:
            pending = self._call(trace, "set_pending_approval", alert_id=alert_id, recommendation=recommendation, evidence=evidence)
            self._call(trace, "log_audit", alert_id=alert_id, action=action, details=f"score={score}; pending={pending['status']}")
        result = {"alert": alert, "customer": customer, "transactions": transactions, "screening": screenings,
                  "evidence": evidence, "trace": trace, "risk_score": score, "risk_reasons": reasons,
                  "autonomy_level": autonomy, "summary": summary, "action_taken": action,
                  "pending_approval": action == "pending_approval", "sar": None}
        self.results[alert_id] = result
        return result

    def approve(self, alert_id: str) -> dict[str, Any]:
        state = self.results.get(alert_id)
        if not state or not state.get("pending_approval"):
            raise ValueError("This alert has no pending approval in the current session.")
        trace = state["trace"]
        approval = self._call(trace, "approve_action", alert_id=alert_id)
        self._call(trace, "log_audit", alert_id=alert_id, action="action_approved", details=approval.get("approved_at", "approved"))
        narrative = generate_sar_narrative(state["evidence"])
        trace.append({"step": len(trace) + 1, "tool": "Astra.generate_sar_narrative", "input": {"evidence_keys": list(state["evidence"])},
                     "output": narrative, "timestamp": datetime.now().isoformat()})
        state["sar"] = self._call(trace, "file_sar", alert_id=alert_id, narrative=narrative)
        self._call(trace, "log_audit", alert_id=alert_id, action="sar_filed", details=narrative)
        state["pending_approval"] = False
        state["action_taken"] = "approved_sar_filed"
        return state

    def reject(self, alert_id: str, reason: str = "Rejected by analyst") -> dict[str, Any]:
        state = self.results.get(alert_id)
        if not state or not state.get("pending_approval"):
            raise ValueError("This alert has no pending approval in the current session.")
        trace = state["trace"]
        rejection = self._call(trace, "reject_action", alert_id=alert_id, reason=reason)
        self._call(trace, "log_audit", alert_id=alert_id, action="action_rejected", details=reason)
        state["pending_approval"] = False
        state["action_taken"] = "recommendation_rejected"
        state["rejection"] = rejection
        return state
