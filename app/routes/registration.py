from flask import Blueprint, request, render_template, jsonify
from app.models import db, User, CertificateType
from app.engine.cert_id import assign_certificate_id
import logging
logger = logging.getLogger(__name__)
bp = Blueprint('registration', __name__)


@bp.route('/register/<token>', methods=['GET'])
def registration_form(token):
    cert_type = CertificateType.query.filter_by(registration_token=token, is_active=True).first_or_404()
    return render_template('public/register.html', cert_type=cert_type)


@bp.route('/register/<token>', methods=['POST'])
def submit_registration(token):
    cert_type = CertificateType.query.filter_by(registration_token=token, is_active=True).first_or_404()
    first_name = (request.form.get('first_name') or '').strip()
    surname = (request.form.get('surname') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    if not first_name or not surname or (not email):
        return (jsonify({'error': 'First name, surname and email are required'}), 400)
    existing = User.query.filter_by(email=email, certificate_type_id=cert_type.id).first()
    if existing:
        return (jsonify({'error': f'Email {email} is already registered for this certificate.'}), 400)
    try:
        user = User(first_name=first_name, surname=surname, other_name=(request.form.get('other_name') or '').strip(
        ), email=email, certificate_type_id=cert_type.id, status='registered', source='public_form')
        db.session.add(user)
        db.session.flush()
        assign_certificate_id(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Registration failed for {email}: {e}')
        return (jsonify({'error': f'Database error: {str(e)}'}), 500)
    return jsonify({'message': 'Registration successful', 'certificate_id': user.certificate_id})
