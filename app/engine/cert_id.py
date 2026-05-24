from datetime import datetime


def generate_cert_id(course_code: str, sequence: int, issued_at: datetime = None) -> str:
    if issued_at is None:
        issued_at = datetime.utcnow()
    code = (course_code or 'GEN').upper().strip()[:6]
    year = issued_at.strftime('%Y')
    try:
        seq_num = int(sequence)
    except (TypeError, ValueError):
        seq_num = 0
    seq_str = str(seq_num).zfill(6)
    return f'MLJ-{code}-{year}-{seq_str}'


def assign_certificate_id(user):
    from app.models import db
    if user.certificate_id:
        return user.certificate_id
    if not user.id:
        db.session.add(user)
        db.session.flush()
    course_code = 'GEN'
    if user.certificate_type:
        course_code = user.certificate_type.course_code
    user.certificate_id = generate_cert_id(course_code=course_code, sequence=user.id,
                                           issued_at=user.created_at or datetime.utcnow())
    return user.certificate_id


def next_sequence(cert_type) -> int:
    current = cert_type.seq_counter or 0
    cert_type.seq_counter = current + 1
    return cert_type.seq_counter


def verify_format(cert_id: str) -> bool:
    try:
        parts = cert_id.split('-')
        return len(parts) == 4 and parts[0] == 'MLJ' and (len(parts[1]) >= 2) and (len(parts[2]) == 4) and parts[2].isdigit() and (len(parts[3]) == 6) and parts[3].isdigit()
    except Exception:
        return False
