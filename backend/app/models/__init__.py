"""Model registry.

Importing this package imports every model so that ``Base.metadata`` is fully
populated (Alembic autogenerate + ``create_all`` both rely on this).
"""
from app.models.base import Base
from app.models.changed_file import ChangedFile
from app.models.code_chunk import CodeChunk
from app.models.developer_feedback import DeveloperFeedback
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.review_finding import ReviewFinding
from app.models.static_analysis_finding import StaticAnalysisFinding
from app.models.verification_result import VerificationResult

__all__ = [
    "Base",
    "Repository",
    "PullRequest",
    "Review",
    "ChangedFile",
    "CodeChunk",
    "StaticAnalysisFinding",
    "ReviewFinding",
    "VerificationResult",
    "DeveloperFeedback",
]
