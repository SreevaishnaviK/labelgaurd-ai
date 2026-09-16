"""LabelGuard AI Legal Engine — deterministic LMPC 2011 rule evaluation.

An automated assessment foundation: rule data model, registry, evaluator
framework, and the first machine-checkable rule groups (Rules 6–13). It
never certifies legal compliance and never converts missing evidence into a
violation.
"""
from fastapi import FastAPI

from app.api import evaluate, health

app = FastAPI(
    title="LabelGuard AI Legal Engine",
    version="0.2.0",
    description="Deterministic Legal Metrology (Packaged Commodities) Rules, 2011 evaluation.",
)

app.include_router(health.router)
app.include_router(evaluate.router)
