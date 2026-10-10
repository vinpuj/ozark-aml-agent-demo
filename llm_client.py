"""Astra text synthesis only; risk decisions remain in the Python orchestrator."""
import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


SYSTEM_PROMPT = (
    "You are an AML investigation co-pilot. Use ONLY the facts in the provided JSON. "
    "Do not infer or invent entities. Clearly distinguish screening matches from confirmed facts. "
    "Do not recommend or execute an action beyond the deterministic risk outcome supplied."
)
SECTION_NAMES = {
    "Customer", "Activity", "Screening", "Risk Indicators", "Recommended Action",
    "SAR Narrative", "Who", "What", "When", "Where", "Why", "How",
}


def _client() -> OpenAI | None:
    key = os.getenv("ASTRA_API_KEY")
    base_url = os.getenv("ASTRA_BASE_URL")
    if not key or not base_url:
        return None
    return OpenAI(api_key=key, base_url=base_url, timeout=8.0, max_retries=0)


def _fallback_summary(evidence: dict[str, Any]) -> str:
    customer = evidence.get("customer", {})
    txs = evidence.get("transactions", [])
    screening = evidence.get("screening", [])
    total = sum(float(t.get("amount", 0)) for t in txs)
    flags = [f"{s.get('name')}: {', '.join(k.replace('_hit', '') for k, v in s.items() if k.endswith('_hit') and v)}"
             for s in screening if any(v for k, v in s.items() if k.endswith("_hit"))]
    return (
        f"Customer: {customer.get('name', 'Not available')} ({customer.get('occupation', 'occupation unavailable')}); "
        f"declared annual income ${customer.get('declared_income', 0):,.0f}.\n"
        f"Activity: {len(txs)} transaction(s), total ${total:,.2f} across the provided records.\n"
        f"Screening: {'; '.join(flags) if flags else 'No demo-list screening hits.'}\n"
        f"Risk Indicators: Deterministic score {evidence.get('risk_score', 'unavailable')}/100. "
        f"Indicators: {', '.join(evidence.get('risk_reasons', [])) or 'none recorded'}.\n"
        f"Recommended Action: {evidence.get('action_recommendation', 'Review the evidence and apply the configured workflow.')}"
    )


def _fallback_sar(evidence: dict[str, Any]) -> str:
    c = evidence.get("customer", {})
    txs = evidence.get("transactions", [])
    lines = []
    for tx in txs:
        lines.append(
            f"{tx.get('timestamp', 'time unavailable')}: {tx.get('currency', '')} {float(tx.get('amount', 0)):,.2f} "
            f"via {tx.get('channel', 'channel unavailable')} to {tx.get('counterparty', 'counterparty unavailable')} "
            f"in {tx.get('counterparty_country', 'country unavailable')}."
        )
    return (
        f"Who: {c.get('name', 'Customer unavailable')}, customer ID {c.get('customer_id', 'unavailable')}, "
        f"{c.get('occupation', 'occupation unavailable')}.\n"
        f"What: Activity associated with alert {evidence.get('alert', {}).get('alert_id', 'unavailable')}.\n"
        f"When: {', '.join(str(t.get('timestamp')) for t in txs) or 'Not available in provided records'}.\n"
        f"Where: {', '.join(sorted({str(t.get('counterparty_country')) for t in txs})) or 'Not available'}.\n"
        f"Why: The deterministic monitoring rules generated score {evidence.get('risk_score', 'unavailable')}/100; "
        f"{', '.join(evidence.get('risk_reasons', [])) or 'no additional risk indicators were recorded'}.\n"
        f"How: {' '.join(lines)}"
    )


def verify_no_hallucination(output: str, evidence: dict[str, Any]) -> bool:
    """Heuristic guard: reject unsupported proper-name phrases and monetary amounts."""
    known: set[str] = set()
    def collect(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"name", "counterparty", "country", "counterparty_country"} and isinstance(value, str):
                    known.add(value.casefold())
                collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)
    collect(evidence)
    for phrase in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", output):
        if phrase not in SECTION_NAMES and phrase.casefold() not in known:
            return False
    allowed_amounts: set[Decimal] = set()
    def collect_amounts(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"amount", "declared_income"} and isinstance(value, (int, float)):
                    allowed_amounts.add(Decimal(str(value)).quantize(Decimal("0.01")))
                collect_amounts(value)
        elif isinstance(obj, list):
            for value in obj:
                collect_amounts(value)
    collect_amounts(evidence)
    for amount in re.findall(r"\$\s*([0-9][0-9,]*(?:\.\d{1,2})?)", output):
        try:
            candidate = Decimal(amount.replace(",", "")).quantize(Decimal("0.01"))
        except InvalidOperation:
            return False
        if candidate not in allowed_amounts:
            return False
    return True


def _generate(evidence: dict[str, Any], task: str, fallback: str) -> str:
    client = _client()
    model = os.getenv("ASTRA_MODEL")
    if client is None or not model:
        return fallback
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{task}\nReturn concise plain text with the requested headings.\nEvidence JSON:\n{json.dumps(evidence, default=str)}"},
            ],
            temperature=0.2,
            timeout=8.0,
        )
        text = response.choices[0].message.content or ""
        if text.strip() and verify_no_hallucination(text, evidence):
            return text.strip()
    except Exception:
        pass
    return fallback


def generate_investigation_summary(evidence: dict[str, Any]) -> str:
    task = "Write an investigation summary with sections Customer, Activity, Screening, Risk Indicators, Recommended Action."
    return _generate(evidence, task, _fallback_summary(evidence))


def generate_sar_narrative(evidence: dict[str, Any]) -> str:
    task = "Draft a factual FinCEN-style SAR narrative with sections Who, What, When, Where, Why, How. Never claim a SAR has been filed."
    return _generate(evidence, task, _fallback_sar(evidence))
