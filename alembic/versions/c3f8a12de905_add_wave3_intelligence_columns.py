"""Add field mapping and font matching columns (Wave 3)

Revision ID: c3f8a12de905
Revises: a82b57fdbe40
Create Date: 2026-05-25

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3f8a12de905'
down_revision: Union[str, Sequence[str], None] = 'a82b57fdbe40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'certificate_types',
        sa.Column('field_mapping', sa.JSON(), nullable=True),
    )
    op.add_column(
        'certificate_types',
        sa.Column('font_matches', sa.JSON(), nullable=True),
    )
    op.add_column(
        'certificate_types',
        sa.Column('qr_placement', sa.JSON(), nullable=True),
    )
    op.add_column(
        'certificate_types',
        sa.Column('mapping_status', sa.String(length=20), nullable=True, server_default='pending'),
    )


def downgrade() -> None:
    op.drop_column('certificate_types', 'mapping_status')
    op.drop_column('certificate_types', 'qr_placement')
    op.drop_column('certificate_types', 'font_matches')
    op.drop_column('certificate_types', 'field_mapping')
