import re
DEFAULT_CERT_SUBJECT = 'Your {{ course_name }} Certificate — {{ organization_name }}'
# Verification links are never included by default — the admin shares them
# through internal channels or the course delivery platform. The
# {{ verification_link }} variable remains available for custom drafts.
DEFAULT_CERT_BODY = 'Dear {{ first_name }},\n\nCongratulations on successfully completing {{ course_name }}!\n\nPlease find your personalised certificate attached to this email.\n\nCertificate ID: {{ certificate_id }}\nIssued on: {{ issue_date }}\n\nWarm regards,\nThe {{ organization_name }} Team\n'


def render(template, context):
    if not template:
        return ''

    def replacer(match):
        key = match.group(1).strip()
        return str(context.get(key, f'{{{key}}} '))
    return re.sub('\\{\\{\\s*(.*?)\\s*\\}\\}', replacer, template)
