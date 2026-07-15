from datetime import datetime


def _luhn_checksum(number_str: str) -> int:
    digits = [int(d) for d in number_str]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10


def _luhn_check_digit(partial: str) -> str:
    check = (10 - _luhn_checksum(partial + '0')) % 10
    return str(check)


def _encode_initials(initials: str) -> str:
    result = ''
    for ch in initials[:2].upper():
        result += str(ord(ch) - 55) if ch.isalpha() else str(ord(ch) - 48)
    return result.zfill(4)


def generate_certificate_id(first_name: str, surname: str, sequence: int, issued_at: datetime = None) -> str:
    if issued_at is None:
        issued_at = datetime.utcnow()
    initials = (first_name[0] + surname[0]).upper() if first_name and surname else 'XX'
    month_str = issued_at.strftime('%b').upper()[:3]
    year_str = issued_at.strftime('%y')
    seq_str = str(sequence).zfill(4)
    numeric_base = _encode_initials(initials) + seq_str
    check = _luhn_check_digit(numeric_base)
    return f'MLJ{initials}{seq_str}{check}{month_str}{year_str}'


def verify_certificate_id(cert_id: str) -> bool:
    try:
        stripped = cert_id[3:]
        initials = stripped[:2]
        numeric_part = stripped[2:7]
        numeric_base = _encode_initials(initials) + numeric_part[:4]
        check_digit = int(numeric_part[4])
        expected = int(_luhn_check_digit(numeric_base))
        return check_digit == expected
    except Exception:
        return False
