"""Per-finding endpoints: developer feedback and single-finding retrieval."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.enums import FeedbackVerdict
from app.database import get_db
from app.models import DeveloperFeedback, ReviewFinding
from app.schemas import FeedbackCreate, FeedbackOut, ReviewFindingOut

router = APIRouter(prefix="/findings", tags=["findings"])

_VALID_VERDICTS = {v.value for v in FeedbackVerdict}


@router.get("/{finding_id}", response_model=ReviewFindingOut)
def get_finding(finding_id: int, db: Session = Depends(get_db)) -> ReviewFinding:
    finding = db.get(ReviewFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.post("/{finding_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(
    finding_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)
) -> DeveloperFeedback:
    finding = db.get(ReviewFinding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.verdict not in _VALID_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict must be one of {sorted(_VALID_VERDICTS)}",
        )

    fb = DeveloperFeedback(
        review_finding_id=finding_id,
        verdict=payload.verdict,
        comment=payload.comment,
        reviewer=payload.reviewer,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb
