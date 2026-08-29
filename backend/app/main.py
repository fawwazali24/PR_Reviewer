"""FastAPI application factory and router wiring."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import findings, health, repositories, reviews
from app.config import settings

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(
    title="AI-Powered PR Reviewer",
    version="0.1.0",
    description=(
        "Reads PRs from GitHub via a read-only PAT and surfaces reviewer-style "
        "findings on a dashboard. Never writes to GitHub."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(repositories.router)
app.include_router(reviews.router)
app.include_router(findings.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": "ai-pr-reviewer", "docs": "/docs"}
