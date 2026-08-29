"""initial schema

Baseline migration. Enables the pgvector extension, then builds the whole
schema directly from the SQLAlchemy models so the migration can never drift
from the model definitions (the models are the single source of truth for the
MVP). Subsequent migrations should use ``alembic revision --autogenerate``,
which will diff models against this now-populated database normally.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Import all models so Base.metadata is fully populated. The pgvector
# SQLAlchemy type is registered as a side effect of importing CodeChunk.
from app.models import Base

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector must exist before any vector(...) column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute("DROP EXTENSION IF EXISTS vector")
