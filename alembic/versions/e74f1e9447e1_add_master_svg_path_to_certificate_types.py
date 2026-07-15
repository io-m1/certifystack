"""add_master_svg_path_to_certificate_types

Revision ID: e74f1e9447e1
Revises: fa3b90e003df
Create Date: 2026-05-19 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e74f1e9447e1'
down_revision: Union[str, Sequence[str], None] = 'fa3b90e003df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('certificate_types', sa.Column('master_svg_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('certificate_types', 'master_svg_path')
