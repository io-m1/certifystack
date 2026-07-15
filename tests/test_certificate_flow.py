"""End-to-end coverage of the merged certificate architecture:

registration gateway -> admin approval (generates + archives the PDF via the
shared render seam) -> admin-triggered dispatch -> public verification.

Template-less gateways render the MedLocum designed certificate; uploaded
templates go through the SVG personalization pipeline (with the legacy
overlay engine as fallback).
"""

from datetime import datetime

from app import db
from app.models import CertArchive, Certificate, CertificateType, OrgSettings, User


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


def test_certificate_never_prints_verification_url(app):
    """QR may encode the verify URL, but no URL text appears on the paper."""
    from io import BytesIO

    from PyPDF2 import PdfReader

    from app.engine.mlj_certificate import render_mlj_certificate

    pdf = render_mlj_certificate(
        full_name='Jane Smith',
        course_title='Advanced Cardiac Life Support',
        certificate_id='MLJ-ACLS-2026-000001',
        verify_url='https://certs.test/verify/MLJ-ACLS-2026-000001',
        include_qr=True,
    )
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ''
    assert 'Jane Smith' in text
    assert 'http' not in text.lower()
    assert 'certs.test' not in text


def test_overlay_engine_masks_baked_in_names(app, tmp_path):
    """An uploaded sample with a baked-in specimen name renders cleanly:
    clear boxes paint over the baked text before the real name is drawn."""
    from io import BytesIO

    from PyPDF2 import PdfReader
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from app.engine.pdf_processor import generate_personalized_pdf

    master = tmp_path / 'master.pdf'
    c = canvas.Canvas(str(master), pagesize=A4)
    c.setFont('Helvetica-Bold', 30)
    c.drawCentredString(A4[0] / 2, 400, 'SPECIMEN NAME')
    c.save()

    pdf = generate_personalized_pdf(
        master_pdf_path=str(master),
        overlay_coords={
            'name_x': A4[0] / 2, 'name_y': 400, 'name_w': 400, 'name_h': 40,
            'name_clear': True,
            'clear_boxes': [{'x': 40, 'y': 40, 'w': 200, 'h': 30, 'color': '#f5f3ec'}],
        },
        full_name='Grace Hopper',
        certificate_id='MLJ-GEN-2026-000042',
        issuance_date='01 March 2026',
        include_qr=True,
        verify_url='https://certs.test/verify/MLJ-GEN-2026-000042',
    )
    assert pdf.startswith(b'%PDF')
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ''
    assert 'Grace Hopper' in text
    assert 'http' not in text.lower()


def test_render_seam_uses_mlj_mode_without_template(app):
    from app.domain.certificates.service import render_certificate_bytes

    ct = _make_gateway()
    user = User(
        first_name='Grace', surname='Hopper', email='grace@test.local',
        certificate_type_id=ct.id, certificate_id='MLJ-BLS-2026-000009',
        status='approved', approved_at=datetime.utcnow(),
    )
    db.session.add(user)
    db.session.commit()

    org = OrgSettings(verify_base_url='https://certs.test')
    pdf = render_certificate_bytes(user, ct, org)
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
    assert Certificate.query.get(user.certificate_id) is None


def test_approval_generates_and_archives_certificate(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='approve@test.local')
    user = User.query.filter_by(email='approve@test.local').first()

    res = admin_client.post('/api/approve', json={
        'user_ids': [user.id], 'cert_type_id': ct.id,
    })
    assert res.status_code == 200
    assert res.get_json()['generated'] == 1

    db.session.expire_all()
    user = db.session.get(User, user.id)
    assert user.status == 'approved'
    assert user.generated_at is not None

    cert = Certificate.query.get(user.certificate_id)
    assert cert is not None
    assert cert.status == 'READY_FOR_DISPATCH'
    assert cert.pdf_artifact.startswith(b'%PDF')


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


def test_admin_can_view_generated_certificate(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='dl@test.local')
    user = User.query.filter_by(email='dl@test.local').first()

    admin_client.post('/api/approve', json={
        'user_ids': [user.id], 'cert_type_id': ct.id,
    })
    db.session.expire_all()
    user = db.session.get(User, user.id)

    res = admin_client.get(f'/api/archive/view/{user.certificate_id}')
    assert res.status_code == 200
    assert res.data.startswith(b'%PDF')


def test_certificate_view_unavailable_before_approval(admin_client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='blocked@test.local')
    user = User.query.filter_by(email='blocked@test.local').first()

    res = admin_client.get(f'/api/archive/view/{user.certificate_id}')
    assert res.status_code == 404


# ── Dispatch (admin-triggered, never automatic) ───────────────────


def test_dispatch_sends_archived_pdf_and_marks_sent(app, admin_client, monkeypatch):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='send@test.local')
    user = User.query.filter_by(email='send@test.local').first()

    admin_client.post('/api/approve', json={
        'user_ids': [user.id], 'cert_type_id': ct.id,
    })
    db.session.expire_all()
    user = db.session.get(User, user.id)
    cert = Certificate.query.get(user.certificate_id)
    cert.transition_to_queued()
    db.session.commit()

    sent_mails = []

    def fake_send(to_email, first_name, full_name, course_name, pdf_bytes,
                  certificate_id, issue_date, **kwargs):
        sent_mails.append({'to': to_email, 'pdf': pdf_bytes,
                           'cert_id': certificate_id})
        return 'msg-test-001'

    import app.engine.email_sender as sender
    monkeypatch.setattr(sender, 'send_certificate_email', fake_send)

    from app.worker import dispatch_certificate
    dispatch_certificate(job_id=0, certificate_id=user.certificate_id)

    assert len(sent_mails) == 1
    assert sent_mails[0]['to'] == 'send@test.local'
    assert sent_mails[0]['pdf'].startswith(b'%PDF')

    db.session.expire_all()
    assert db.session.get(User, user.id).status == 'sent'
    assert Certificate.query.get(user.certificate_id).status == 'SENT'


# ── Public verification ───────────────────────────────────────────


def test_verify_page_confirms_generated_certificate(admin_client, client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='verify@test.local')
    user = User.query.filter_by(email='verify@test.local').first()

    admin_client.post('/api/approve', json={
        'user_ids': [user.id], 'cert_type_id': ct.id,
    })
    db.session.expire_all()
    user = db.session.get(User, user.id)

    res = client.get(f'/verify/{user.certificate_id}')
    assert res.status_code == 200
    assert user.certificate_id.encode() in res.data


def test_revoked_certificate_fails_verification(admin_client, client):
    ct = _make_gateway()
    _register(admin_client, ct.registration_token, email='revoke@test.local')
    user = User.query.filter_by(email='revoke@test.local').first()

    admin_client.post('/api/approve', json={
        'user_ids': [user.id], 'cert_type_id': ct.id,
    })
    db.session.expire_all()
    user = db.session.get(User, user.id)

    res = admin_client.post('/api/revoke', json={'user_ids': [user.id]})
    assert res.status_code == 200

    db.session.expire_all()
    assert db.session.get(User, user.id).status == 'revoked'

    page = client.get(f'/verify/{user.certificate_id}')
    assert page.status_code == 200
    assert b'revoked' in page.data.lower()
