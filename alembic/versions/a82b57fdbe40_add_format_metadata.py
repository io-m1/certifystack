"""add_format_metadata

Revision ID: a82b57fdbe40
Revises: e23a46fbde90
Create Date: 2026-05-24 21:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a82b57fdbe40'
down_revision: Union[str, Sequence[str], None] = 'e23a46fbde90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('certificate_types', sa.Column('original_format', sa.String(length=20), nullable=True))
    op.add_column('certificate_types', sa.Column('conversion_path', sa.String(length=50), nullable=True))
    op.add_column('certificate_types', sa.Column('quality_level', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('certificate_types', 'quality_level')
    op.drop_column('certificate_types', 'conversion_path')
    op.drop_column('certificate_types', 'original_format')
