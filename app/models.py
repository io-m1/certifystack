from app import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json


class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class OrgSettings(db.Model):
    __tablename__ = 'org_settings'
    id = db.Column(db.Integer, primary_key=True)
    org_name = db.Column(db.String(200), default='Medical Locum Jobs')
    sender_name = db.Column(db.String(200), default='Medical Locum Jobs Academy')
    sender_email = db.Column(db.String(255), default='')
    reply_to_email = db.Column(db.String(255), default='')
    verify_base_url = db.Column(db.String(500), default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CertificateType(db.Model):
    """A certificate gateway. Each row owns a public registration link
    (/register/<registration_token>) and defines how its certificate renders:
    'mlj' (the MedLocum designed certificate, no template needed) or
    'overlay' (legacy: text overlaid on an uploaded master PDF/PNG)."""

    __tablename__ = 'certificate_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    course_code = db.Column(db.String(20), default='GEN')
    period = db.Column(db.String(100), nullable=False)
    master_pdf_path = db.Column(db.String(500), nullable=False, default='')
    master_file_type = db.Column(db.String(10), default='pdf')
    overlay_coords = db.Column(db.JSON, nullable=False, default=dict)
    ocr_regions = db.Column(db.JSON, nullable=True)
    registration_token = db.Column(db.String(100), unique=True, nullable=False)
    email_subject = db.Column(db.String(300), nullable=True)
    email_message = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    seq_counter = db.Column(db.Integer, default=0)
    render_mode = db.Column(db.String(10), default='mlj')
    organisation = db.Column(db.String(200), default='')
    website = db.Column(db.String(200), default='')
    signatory_name = db.Column(db.String(200), default='')
    signatory_title = db.Column(db.String(200), default='')
    duration_hours = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', backref='certificate_type', lazy=True)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    other_name = db.Column(db.String(100))
    email = db.Column(db.String(255), nullable=False)
    certificate_type_id = db.Column(db.Integer, db.ForeignKey('certificate_types.id'), nullable=False)
    status = db.Column(db.String(20), default='registered')
    certificate_id = db.Column(db.String(60), unique=True)
    include_qr = db.Column(db.Boolean, default=True)
    score = db.Column(db.Float, nullable=True)
    completion_status = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(50), default='manual')
    approved_at = db.Column(db.DateTime)
    generated_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unsubscribed = db.Column(db.Boolean, default=False)

    @property
    def full_name(self):
        parts = [self.first_name, self.other_name or '', self.surname]
        return ' '.join(p for p in parts if p and p.strip())

    @property
    def initials(self):
        return ''.join(p[0].upper() for p in [self.first_name, self.surname] if p)


class CertArchive(db.Model):
    __tablename__ = 'cert_archive'
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(60), unique=True, nullable=False)
    full_name = db.Column(db.String(300), nullable=False)
    cert_name = db.Column(db.String(200), nullable=False)
    course_code = db.Column(db.String(20), nullable=True)
    issued_date = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='issued')
    raw_binary = db.Column(db.LargeBinary, nullable=True)
    pdf_binary = db.Column(db.LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'certificate_id': self.certificate_id,
            'full_name': self.full_name,
            'cert_name': self.cert_name,
            'course_code': self.course_code,
            'issued_date': self.issued_date,
            'status': self.status,
        }


class EmailDraft(db.Model):
    __tablename__ = 'email_drafts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, default='Untitled Draft')
    cert_type_id = db.Column(db.Integer, db.ForeignKey('certificate_types.id'), nullable=True)
    subject = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=False)
    include_attachment = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Campaign(db.Model):
    __tablename__ = 'campaigns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    cert_type_id = db.Column(db.Integer, db.ForeignKey('certificate_types.id'), nullable=True)
    draft_id = db.Column(db.Integer, db.ForeignKey('email_drafts.id'), nullable=True)
    status = db.Column(db.String(20), default='draft')
    include_attachment = db.Column(db.Boolean, default=False)
    recipient_count = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    performed_by = db.Column(db.String(100))
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id               = db.Column(db.Integer, primary_key=True)
    recipient_email  = db.Column(db.String(255), nullable=False)
    recipient_name   = db.Column(db.String(300), nullable=True)
    email_type       = db.Column(db.String(30), default='certificate')
    status           = db.Column(db.String(20), default='pending')
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    cert_type_id     = db.Column(db.Integer, db.ForeignKey('certificate_types.id', ondelete='SET NULL'), nullable=True)
    draft_id         = db.Column(db.Integer, db.ForeignKey('email_drafts.id', ondelete='SET NULL'), nullable=True)
    campaign_id      = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True)
    failed_reason    = db.Column(db.Text, nullable=True)
    retry_count      = db.Column(db.Integer, default=0)
    started_at       = db.Column(db.DateTime, nullable=True)
    sent_at          = db.Column(db.DateTime, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
