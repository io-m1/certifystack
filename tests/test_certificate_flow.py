"""End-to-end coverage of the ported MedLocum certificate architecture:

registration gateway -> admin approval (generates + archives the PDF)
-> admin-triggered dispatch (emails the archived PDF) -> public verification.
"""

from datetime import datetime

from app import db
from app.models import User, CertificateType, CertArchive, OrgSettings, EmailLog


def _make_gateway(**overrides):
    fields = dict(
        name='Basic Life Support', course_code='BLS', period='March 2026',
        render_mode='mlj', master_pdf_path='', overlay_coords={},
        registration_token='tok-' + datetime.utcnow().strftime('%f'),
        duration_hours=6.0, seq_counter=0,
    )
    fields.update(overrides)
    ct = CertificateType(**fields)
    db.session.add(ct)
    db.session.commit()
    return ct


def _register(client, token, first='Ada', last='Lovelace', email='ada@test.local'):
    res = client.post(f'/register/{token}', data={
        'first_name': first, 'surname': last, 'email': email,
    })
    assert res.status_code == 200
    return res.get_json()


# ── Renderer ──────────────────────────────────────────────────────


def test_mlj_renderer_produces_valid_pdf(app):
    from app.engine.mlj_certificate import render_mlj_certificate

    pdf = render_mlj_certificate(
        full_name='Jane Smith',
        course_title='Advanced Cardiac Life Support',
        certificate_id='MLJ-ACLS-2026-000001',
        verify_url='https://certs.test/verify/MLJ-ACLS-2026-000001',
        duration_hours=12.5,
    )
    assert pdf.startswith(b'%PDF')
    assert len(pdf) > 3000


def test_renderer_facade_uses_mlj_mode_without_template(app):
    from app.engine.renderer import render_certificate_pdf

    ct = _make_gateway()
    user = User(
        first_name='Grace', surname='Hopper', email='grace@test.local',
        certificate_type_id=ct.id, certificate_id='MLJ-BLS-2026-000009',
        status='approved', approved_at=datetime.utcnow(),
    )
    db.session.add(user)
    db.session.commit()

    org = OrgSettings(verify_base_url='https://certs.test')
    pdf = render_certificate_pdf(user, ct, org)
    assert pdf.startswith(b'%PDF')


# ── Gateway creation ──────────────────────────────────────────────


def test_create_gateway_without_template_defaults_to_mlj(admin_client):
    res = admin_client.post('/api/cert-types', data={
        'name': 'Infection Control', 'course_code': 'IC',
        'period': 'April 2026', 'duration_hours': '4',
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['render_mode'] == 'mlj'
    assert data['register_url'].startswith('/register/')

    ct = db.session.get(CertificateType, data['id'])
    assert ct.master_pdf_path == ''
    assert ct.duration_hours == 4.0


def test_gateway_requires_name_and_period(admin_client):
    res = admin_client.post('/api/cert-types', data={'name': 'X'})
    assert res.status_code == 400


# ── Registration -> approval -> generation ────────────────────────


def test_registration_stays_pending_until_admin_approves(client):
    ct = _make_gateway()
    data = _register(client, ct.registration_token)

    user = User.query.filter_by(email='ada@test.local').first()
    assert user.status == 'registered'
    assert user.certificate_id == data['certificate_id']
    assert user.generated_at is None
    assert CertArchive.query.filter_by(certificate_id=user.certificate_id).first() is None


def test_approval_generates_and_archives_certificate(admin_client, monkeypatch):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='approve@test.local')
    user = User.query.filter_by(email='approve@test.local').first()

    # Run the background generation synchronously for determinism.
    import app.services.email.queue as q
    monkeypatch.setattr(q, 'run_in_background', lambda func, **kw: func(**kw))

    res = admin_client.post('/api/approve', json={'user_ids': [user.id]})
    assert res.status_code == 200
    assert res.get_json()['approved'] == 1

    db.session.expire_all()
    user = db.session.get(User, user.id)
    assert user.status == 'approved'
    assert user.generated_at is not None

    archive = CertArchive.query.filter_by(certificate_id=user.certificate_id).first()
    assert archive is not None
    assert archive.status == 'generated'
    assert archive.pdf_binary.startswith(b'%PDF')


def test_rejected_registrant_gets_no_certificate(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='reject@test.local')
    user = User.query.filter_by(email='reject@test.local').first()

    res = admin_client.post('/api/reject', json={'user_ids': [user.id]})
    assert res.status_code == 200

    db.session.expire_all()
    user = db.session.get(User, user.id)
    assert user.status == 'rejected'
    assert user.generated_at is None


def test_admin_can_download_generated_certificate(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='dl@test.local')
    user = User.query.filter_by(email='dl@test.local').first()
    user.status = 'approved'
    user.approved_at = datetime.utcnow()
    db.session.commit()

    res = admin_client.get(f'/api/users/{user.id}/certificate.pdf')
    assert res.status_code == 200
    assert res.data.startswith(b'%PDF')


def test_certificate_download_blocked_before_approval(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='blocked@test.local')
    user = User.query.filter_by(email='blocked@test.local').first()

    res = admin_client.get(f'/api/users/{user.id}/certificate.pdf')
    assert res.status_code == 409


# ── Dispatch (admin-triggered, never automatic) ───────────────────


def test_dispatch_sends_archived_pdf_and_marks_sent(app, admin_client, monkeypatch):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='send@test.local')
    user = User.query.filter_by(email='send@test.local').first()
    user.status = 'approved'
    user.approved_at = datetime.utcnow()

    from app.services.certgen import generate_for_user
    org = OrgSettings.query.first() or OrgSettings()
    generate_for_user(user, ct, org)
    db.session.commit()

    sent_mails = []

    def fake_dispatch(to_email, subject, body, **kwargs):
        sent_mails.append({'to': to_email, 'subject': subject,
                           'attachments': kwargs.get('attachments')})
        return {'success': True, 'error': None, 'attempts': 1}

    import app.services.email.sender as sender
    monkeypatch.setattr(sender, 'dispatch', fake_dispatch)

    log = EmailLog(recipient_email=user.email, recipient_name=user.full_name,
                   email_type='certificate', status='pending',
                   user_id=user.id, cert_type_id=ct.id)
    db.session.add(log)
    user.status = 'sending'
    user.sent_at = datetime.utcnow()
    db.session.commit()

    from app.services.email.jobs import send_certificate_job
    send_certificate_job(log_id=log.id, user_id=user.id, cert_type_id=ct.id)

    assert len(sent_mails) == 1
    assert sent_mails[0]['to'] == 'send@test.local'
    assert sent_mails[0]['attachments'][0]['data'].startswith(b'%PDF')

    db.session.expire_all()
    assert db.session.get(User, user.id).status == 'sent'
    assert db.session.get(EmailLog, log.id).status == 'sent'


# ── Public verification ───────────────────────────────────────────


def test_verify_page_confirms_generated_certificate(admin_client, client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='verify@test.local')
    user = User.query.filter_by(email='verify@test.local').first()
    user.status = 'approved'
    user.approved_at = datetime.utcnow()
    from app.services.certgen import generate_for_user
    generate_for_user(user, ct, OrgSettings())
    db.session.commit()

    res = client.get(f'/verify/{user.certificate_id}')
    assert res.status_code == 200
    assert user.certificate_id.encode() in res.data


def test_revoked_certificate_fails_verification(admin_client, client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='revoke@test.local')
    user = User.query.filter_by(email='revoke@test.local').first()
    user.status = 'approved'
    user.approved_at = datetime.utcnow()
    from app.services.certgen import generate_for_user
    generate_for_user(user, ct, OrgSettings())
    db.session.commit()

    res = admin_client.post('/api/revoke', json={'user_ids': [user.id]})
    assert res.status_code == 200

    db.session.expire_all()
    archive = CertArchive.query.filter_by(certificate_id=user.certificate_id).first()
    assert archive.status == 'revoked'

    page = client.get(f'/verify/{user.certificate_id}')
    assert page.status_code == 200
    body = page.data.lower()
    assert b'not' in body or b'invalid' in body
