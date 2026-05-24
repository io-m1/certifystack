from app import db
from flask_login import UserMixin
from datetime import datetime
import uuid
from werkzeug.security import generate_password_hash, check_password_hash


class CertificateStatus:
    DRAFT = "DRAFT"
    APPROVED_FOR_GENERATION = "APPROVED_FOR_GENERATION"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    READY_FOR_DISPATCH = "READY_FOR_DISPATCH"
    QUEUED_FOR_DISPATCH = "QUEUED_FOR_DISPATCH"
    DISPATCHING = "DISPATCHING"
    SENT = "SENT"
    DELIVERED_CONFIRMED = "DELIVERED_CONFIRMED"
    
    FAILED_GENERATION = "FAILED_GENERATION"
    FAILED_DISPATCH = "FAILED_DISPATCH"
    PERMANENTLY_FAILED = "PERMANENTLY_FAILED"


class JobQueue(db.Model):
    __tablename__ = "job_queue"
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(120), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    idempotency_key = db.Column(db.String(255), unique=True, nullable=True)
    status = db.Column(db.String(20), default="PENDING")
    checkpoint = db.Column(db.String(50), default="INIT")
    attempts = db.Column(db.Integer, default=0)
    locked_at = db.Column(db.DateTime, nullable=True)
    locked_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        super(JobQueue, self).__init__(**kwargs)

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def __init__(self, **kwargs):
        super(Admin, self).__init__(**kwargs)

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

    def __init__(self, **kwargs):
        super(OrgSettings, self).__init__(**kwargs)


class CertificateAsset(db.Model):
    __tablename__ = 'certificate_assets'
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.Text, nullable=False)
    file_binary = db.Column(db.LargeBinary, nullable=False)
    file_hash = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(CertificateAsset, self).__init__(**kwargs)


class CertificateType(db.Model):
    __tablename__ = 'certificate_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    course_code = db.Column(db.String(20), default='GEN')
    period = db.Column(db.String(100), nullable=False)
    asset_id = db.Column(db.String(36), db.ForeignKey('certificate_assets.id'), nullable=True)
    master_pdf_path = db.Column(db.String(500), nullable=True)
    master_pdf_binary = db.Column(db.LargeBinary, nullable=True)
    master_svg_path = db.Column(db.String(500), nullable=True)  # New: SVG template path
    master_file_type = db.Column(db.String(10), default='pdf')
    overlay_coords = db.Column(db.JSON, nullable=False)
    ocr_regions = db.Column(db.JSON, nullable=True)
    registration_token = db.Column(db.String(100), unique=True, nullable=False)
    email_subject = db.Column(db.String(300), nullable=True)
    email_message = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    seq_counter = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(CertificateType, self).__init__(**kwargs)
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
    sent_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    unsubscribed = db.Column(db.Boolean, default=False)

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)

    @property
    def full_name(self):
        parts = [self.first_name, self.other_name or '', self.surname]
        return ' '.join((p for p in parts if p and p.strip()))

    @property
    def initials(self):
        return ''.join((p[0].upper() for p in [self.first_name, self.surname] if p))


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

    def __init__(self, **kwargs):
        super(CertArchive, self).__init__(**kwargs)

    def to_dict(self):
        return {'certificate_id': self.certificate_id, 'full_name': self.full_name, 'cert_name': self.cert_name, 'course_code': self.course_code, 'issued_date': self.issued_date, 'status': self.status}


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

    def __init__(self, **kwargs):
        super(EmailDraft, self).__init__(**kwargs)


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

    def __init__(self, **kwargs):
        super(Campaign, self).__init__(**kwargs)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    performed_by = db.Column(db.String(100))
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(AuditLog, self).__init__(**kwargs)


class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id = db.Column(db.Integer, primary_key=True)
    recipient_email = db.Column(db.String(255), nullable=False)
    recipient_name = db.Column(db.String(300), nullable=True)
    email_type = db.Column(db.String(30), default='certificate')
    status = db.Column(db.String(20), default='pending')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    cert_type_id = db.Column(db.Integer, db.ForeignKey('certificate_types.id', ondelete='SET NULL'), nullable=True)
    draft_id = db.Column(db.Integer, db.ForeignKey('email_drafts.id', ondelete='SET NULL'), nullable=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True)
    failed_reason = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(EmailLog, self).__init__(**kwargs)


class CertificateLedgerEntry(db.Model):
    __tablename__ = 'certificate_ledger'

    id = db.Column(db.String(36), primary_key=True)
    cert_id = db.Column(db.String(60), db.ForeignKey('certificates.id'), index=True, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    prev_hash = db.Column(db.String(128), nullable=False)
    entry_hash = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    signature = db.Column(db.String(128), nullable=True)

    def __init__(self, **kwargs):
        super(CertificateLedgerEntry, self).__init__(**kwargs)


class Certificate(db.Model):
    __tablename__ = 'certificates'
    id = db.Column(db.String(60), primary_key=True) # certificate_id
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    cert_type_id = db.Column(db.Integer, db.ForeignKey('certificate_types.id'), nullable=False)
    template_version = db.Column(db.String(50), nullable=True)
    asset_id = db.Column(db.String(36), nullable=True)
    status = db.Column(db.String(30), default=CertificateStatus.DRAFT)
    pdf_artifact = db.Column(db.LargeBinary, nullable=True)
    pdf_hash = db.Column(db.String(128), nullable=True)
    sendgrid_message_id = db.Column(db.String(128), nullable=True)
    failure_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('certificate_records', lazy=True))
    cert_type = db.relationship('CertificateType')

    def __init__(self, **kwargs):
        super(Certificate, self).__init__(**kwargs)

    def _log_event(self, event_type, payload=None):
        from app.engine.clp import append_ledger_event
        append_ledger_event(self.id, event_type, payload)

    def transition_to_approved(self):
        if self.status != CertificateStatus.DRAFT:
            raise RuntimeError(f"Invalid transition to APPROVED from {self.status}")
        self.status = CertificateStatus.APPROVED_FOR_GENERATION
        self.updated_at = datetime.utcnow()
        self._log_event("APPROVED")

    def transition_to_generating(self):
        valid_states = [CertificateStatus.APPROVED_FOR_GENERATION, CertificateStatus.FAILED_GENERATION]
        if self.status not in valid_states:
            raise RuntimeError(f"Invalid transition to GENERATING from {self.status}")
        self.status = CertificateStatus.GENERATING
        self.updated_at = datetime.utcnow()
        self._log_event("GENERATION_STARTED")

    def transition_to_generated(self, pdf_bytes, pdf_hash):
        if self.status != CertificateStatus.GENERATING:
            raise RuntimeError(f"Invalid transition to GENERATED from {self.status}")
        if not pdf_bytes or not pdf_hash:
            raise ValueError("GENERATED requires finalized PDF artifact and hash")
        self.pdf_artifact = pdf_bytes
        self.pdf_hash = pdf_hash
        self.status = CertificateStatus.GENERATED
        self.updated_at = datetime.utcnow()
        self._log_event("GENERATION_COMPLETED", payload={"pdf_hash": pdf_hash})

    def transition_to_ready(self):
        if self.status != CertificateStatus.GENERATED:
            raise RuntimeError(f"Invalid transition to READY from {self.status}")
        self.status = CertificateStatus.READY_FOR_DISPATCH
        self.updated_at = datetime.utcnow()
        self._log_event("READY_FOR_DISPATCH")

    def transition_to_queued(self):
        if self.status != CertificateStatus.READY_FOR_DISPATCH:
            raise RuntimeError(f"Invalid transition to QUEUED from {self.status}")
        self.status = CertificateStatus.QUEUED_FOR_DISPATCH
        self.updated_at = datetime.utcnow()
        self._log_event("QUEUED")

    def transition_to_dispatching(self):
        valid_states = [CertificateStatus.QUEUED_FOR_DISPATCH, CertificateStatus.FAILED_DISPATCH]
        if self.status not in valid_states:
            raise RuntimeError(f"Invalid transition to DISPATCHING from {self.status}")
        self.status = CertificateStatus.DISPATCHING
        self.updated_at = datetime.utcnow()
        self._log_event("DISPATCH_STARTED")

    def transition_to_sent(self, message_id):
        if self.status != CertificateStatus.DISPATCHING:
            raise RuntimeError(f"Invalid transition to SENT from {self.status}")
        if not message_id:
            raise ValueError("SENT requires SendGrid message ID")
        self.sendgrid_message_id = message_id
        self.status = CertificateStatus.SENT
        self.updated_at = datetime.utcnow()
        self._log_event("DISPATCH_CONFIRMED", payload={"message_id": message_id})

    def fail_generation(self, error):
        self.failure_count += 1
        self.last_error = str(error)
        if self.failure_count >= 5:
            self.status = CertificateStatus.PERMANENTLY_FAILED
        else:
            self.status = CertificateStatus.FAILED_GENERATION
        self.updated_at = datetime.utcnow()
        self._log_event("GENERATION_FAILED", payload={"error": str(error)})

    def fail_dispatch(self, error):
        self.failure_count += 1
        self.last_error = str(error)
        if self.failure_count >= 5:
            self.status = CertificateStatus.PERMANENTLY_FAILED
        else:
            self.status = CertificateStatus.FAILED_DISPATCH
        self.updated_at = datetime.utcnow()
        self._log_event("DISPATCH_FAILED", payload={"error": str(error)})

