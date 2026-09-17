"""Persist cached GitHub pull-request summary fields."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_persist_pr_summary"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pull_requests", sa.Column("github_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pull_requests", sa.Column("additions", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pull_requests", sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pull_requests", sa.Column("changed_files", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("pull_requests", "changed_files")
    op.drop_column("pull_requests", "deletions")
    op.drop_column("pull_requests", "additions")
    op.drop_column("pull_requests", "github_updated_at")