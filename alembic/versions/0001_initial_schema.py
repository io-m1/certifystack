"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admins',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('email', sa.String(255), nullable=False),
                    sa.Column('password_hash', sa.String(255), nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('email'),
                    )

    op.create_table('org_settings',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('org_name', sa.String(200), nullable=True),
                    sa.Column('sender_name', sa.String(200), nullable=True),
                    sa.Column('sender_email', sa.String(255), nullable=True),
                    sa.Column('reply_to_email', sa.String(255), nullable=True),
                    sa.Column('verify_base_url', sa.String(500), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    )

    op.create_table('certificate_types',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(200), nullable=False),
                    sa.Column('course_code', sa.String(20), nullable=True),
                    sa.Column('period', sa.String(100), nullable=False),
                    sa.Column('master_pdf_path', sa.String(500), nullable=False),
                    sa.Column('master_file_type', sa.String(10), nullable=True),
                    sa.Column('overlay_coords', sa.JSON(), nullable=False),
                    sa.Column('ocr_regions', sa.JSON(), nullable=True),
                    sa.Column('registration_token', sa.String(100), nullable=False),
                    sa.Column('email_subject', sa.String(300), nullable=True),
                    sa.Column('email_message', sa.Text(), nullable=True),
                    sa.Column('is_active', sa.Boolean(), nullable=True),
                    sa.Column('seq_counter', sa.Integer(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('registration_token'),
                    )

    op.create_table('email_drafts',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(200), nullable=False),
                    sa.Column('cert_type_id', sa.Integer(), nullable=True),
                    sa.Column('subject', sa.String(300), nullable=False),
                    sa.Column('body', sa.Text(), nullable=False),
                    sa.Column('include_attachment', sa.Boolean(), nullable=True),
                    sa.Column('is_default', sa.Boolean(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('updated_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['cert_type_id'], ['certificate_types.id']),
                    sa.PrimaryKeyConstraint('id'),
                    )

    op.create_table('campaigns',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(200), nullable=False),
                    sa.Column('cert_type_id', sa.Integer(), nullable=True),
                    sa.Column('draft_id', sa.Integer(), nullable=True),
                    sa.Column('status', sa.String(20), nullable=True),
                    sa.Column('include_attachment', sa.Boolean(), nullable=True),
                    sa.Column('recipient_count', sa.Integer(), nullable=True),
                    sa.Column('sent_count', sa.Integer(), nullable=True),
                    sa.Column('failed_count', sa.Integer(), nullable=True),
                    sa.Column('scheduled_at', sa.DateTime(), nullable=True),
                    sa.Column('sent_at', sa.DateTime(), nullable=True),
                    sa.Column('created_by', sa.String(100), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['cert_type_id'], ['certificate_types.id']),
                    sa.ForeignKeyConstraint(['draft_id'], ['email_drafts.id']),
                    sa.PrimaryKeyConstraint('id'),
                    )

    op.create_table('users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('first_name', sa.String(100), nullable=False),
                    sa.Column('surname', sa.String(100), nullable=False),
                    sa.Column('other_name', sa.String(100), nullable=True),
                    sa.Column('email', sa.String(255), nullable=False),
                    sa.Column('certificate_type_id', sa.Integer(), nullable=False),
                    sa.Column('status', sa.String(20), nullable=True),
                    sa.Column('certificate_id', sa.String(60), nullable=True),
                    sa.Column('include_qr', sa.Boolean(), nullable=True),
                    sa.Column('score', sa.Float(), nullable=True),
                    sa.Column('completion_status', sa.String(50), nullable=True),
                    sa.Column('source', sa.String(50), nullable=True),
                    sa.Column('approved_at', sa.DateTime(), nullable=True),
                    sa.Column('sent_at', sa.DateTime(), nullable=True),
                    sa.Column('archived_at', sa.DateTime(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.Column('unsubscribed', sa.Boolean(), nullable=True),
                    sa.ForeignKeyConstraint(['certificate_type_id'], ['certificate_types.id']),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('certificate_id'),
                    )

    op.create_table('cert_archive',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('certificate_id', sa.String(60), nullable=False),
                    sa.Column('full_name', sa.String(300), nullable=False),
                    sa.Column('cert_name', sa.String(200), nullable=False),
                    sa.Column('course_code', sa.String(20), nullable=True),
                    sa.Column('issued_date', sa.String(50), nullable=False),
                    sa.Column('email', sa.String(255), nullable=True),
                    sa.Column('status', sa.String(20), nullable=True),
                    sa.Column('raw_binary', sa.LargeBinary(), nullable=True),
                    sa.Column('pdf_binary', sa.LargeBinary(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('certificate_id'),
                    )

    op.create_table('audit_logs',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=True),
                    sa.Column('action', sa.String(50), nullable=False),
                    sa.Column('performed_by', sa.String(100), nullable=True),
                    sa.Column('details', sa.JSON(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
                    sa.PrimaryKeyConstraint('id'),
                    )

    op.create_table('email_logs',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('recipient_email', sa.String(255), nullable=False),
                    sa.Column('recipient_name', sa.String(300), nullable=True),
                    sa.Column('email_type', sa.String(30), nullable=True),
                    sa.Column('status', sa.String(20), nullable=True),
                    sa.Column('user_id', sa.Integer(), nullable=True),
                    sa.Column('cert_type_id', sa.Integer(), nullable=True),
                    sa.Column('draft_id', sa.Integer(), nullable=True),
                    sa.Column('campaign_id', sa.Integer(), nullable=True),
                    sa.Column('failed_reason', sa.Text(), nullable=True),
                    sa.Column('retry_count', sa.Integer(), nullable=True),
                    sa.Column('started_at', sa.DateTime(), nullable=True),
                    sa.Column('sent_at', sa.DateTime(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), nullable=True),
                    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
                    sa.ForeignKeyConstraint(['cert_type_id'], ['certificate_types.id'], ondelete='SET NULL'),
                    sa.ForeignKeyConstraint(['draft_id'], ['email_drafts.id'], ondelete='SET NULL'),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
                    sa.PrimaryKeyConstraint('id'),
                    )


def downgrade() -> None:
    op.drop_table('email_logs')
    op.drop_table('audit_logs')
    op.drop_table('cert_archive')
    op.drop_table('users')
    op.drop_table('campaigns')
    op.drop_table('email_drafts')
    op.drop_table('certificate_types')
    op.drop_table('org_settings')
    op.drop_table('admins')
