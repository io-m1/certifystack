"""add_svg_columns

Revision ID: e23a46fbde90
Revises: e74f1e9447e1
Create Date: 2026-05-24 20:41:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e23a46fbde90'
down_revision: Union[str, Sequence[str], None] = 'e74f1e9447e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('certificate_types', sa.Column('template_format', sa.String(length=10), nullable=True, server_default='svg'))
    op.add_column('certificate_types', sa.Column('template_svg_path', sa.String(length=500), nullable=True))
    op.add_column('certificate_types', sa.Column('detected_fields', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('certificate_types', 'detected_fields')
    op.drop_column('certificate_types', 'template_svg_path')
    op.drop_column('certificate_types', 'template_format')
