"""Shared typed models for the AML demo."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Alert(BaseModel):
    alert_id: str
    customer_id: str
    transaction_ids: list[str]
    trigger_reason: str
    timestamp: datetime


class Customer(BaseModel):
    customer_id: str
    name: str
    country: str
    declared_income: float
    occupation: str
    risk_rating: str
    pep_flag: bool


class Transaction(BaseModel):
    transaction_id: str
    customer_id: str
    amount: float
    currency: str
    counterparty: str
    counterparty_country: str
    timestamp: datetime
    channel: str


class TraceStep(BaseModel):
    step: str
    tool: str
    input: dict[str, Any]
    output: Any
    timestamp: datetime = Field(default_factory=datetime.now)


AutonomyLevel = Literal["human-out", "human-on", "human-in"]
