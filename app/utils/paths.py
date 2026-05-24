import os
UPLOAD_ROOT = os.path.abspath(os.environ.get('UPLOAD_FOLDER', 'uploads'))


def ensure_upload_root():
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
