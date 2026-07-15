import os
import tempfile

import pytest

# Point the whole app (including background jobs that call create_app()
# themselves) at an isolated temp database before anything imports config.
_db_dir = tempfile.mkdtemp(prefix='certifystack-test-')
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(_db_dir, 'test.db').replace('\\', '/')
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('ADMIN_EMAIL', 'admin@test.local')
os.environ.setdefault('ADMIN_PASSWORD', 'test-password')
# The in-app job worker thread must not run during tests.
os.environ['START_IN_APP_WORKER'] = 'False'

from app import create_app, db  # noqa: E402


@pytest.fixture(scope='session')
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture()
def client(app):
    with app.app_context():
        yield app.test_client()


@pytest.fixture()
def admin_client(app):
    client = app.test_client()
    client.post('/login', data={
        'email': os.environ['ADMIN_EMAIL'],
        'password': os.environ['ADMIN_PASSWORD'],
    })
    with app.app_context():
        yield client


@pytest.fixture(autouse=True)
def _clean_tables(app):
    yield
    with app.app_context():
        from app.models import (
            AuditLog, CertArchive, Certificate, CertificateAsset,
            CertificateLedgerEntry, CertificateType, EmailLog, JobQueue, User,
        )
        for model in (EmailLog, AuditLog, CertificateLedgerEntry, Certificate,
                      CertArchive, JobQueue, User, CertificateType, CertificateAsset):
            model.query.delete()
        db.session.commit()
    # Archived PDFs must not leak between tests: SQLite reuses row ids after
    # deletes, so certificate ids collide with files from earlier tests.
    import glob
    for pdf in glob.glob(os.path.join('archive', '*.pdf')):
        try:
            os.remove(pdf)
        except OSError:
            pass
