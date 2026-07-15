from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from app.utils.tasks import task_queue
import os
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()


def create_app():
    app = Flask(__name__, static_folder='../static')
    app.config.from_object('app.config.Config')
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
    mail.init_app(app)
    task_queue.init_app(app)
    
    from app.bootstrap.tasks import bootstrap_tasks
    from app.registry.validate import validate_tasks
    
    bootstrap_tasks()
    validate_tasks()
    
    from app.utils.paths import ensure_upload_root
    ensure_upload_root()
    from app.routes import auth, registration, certificates
    from app.routes import email_routes
    app.register_blueprint(auth.bp)
    app.register_blueprint(registration.bp)
    app.register_blueprint(certificates.bp)
    app.register_blueprint(email_routes.bp)

    with app.app_context():
        try:
            db.create_all()
            _ensure_schema()
        except Exception:
            pass

    # Start the in-app background task processor thread to process queues
    # on single-container/dyno environments without separate worker containers.
    if os.environ.get('START_IN_APP_WORKER', 'True').lower() == 'true':
        import sys
        # Prevent starting worker threads during database migrations or CLI tools
        is_cli = any(x in sys.argv[0] for x in ['flask', 'migrate', 'alembic', 'manage', 'db'])
        if not is_cli:
            from app.worker_loop import start_in_app_worker
            start_in_app_worker(app)

    return app


def _ensure_schema():
    """Lightweight additive migration: add columns introduced by the
    MedLocum certificate port to databases created before them. Works on
    both SQLite and Postgres; existing columns are left untouched."""
    from sqlalchemy import inspect, text

    additions = {
        'certificate_types': {
            'render_mode': "VARCHAR(10) DEFAULT 'mlj'",
            'organisation': "VARCHAR(200) DEFAULT ''",
            'website': "VARCHAR(200) DEFAULT ''",
            'signatory_name': "VARCHAR(200) DEFAULT ''",
            'signatory_title': "VARCHAR(200) DEFAULT ''",
            'duration_hours': 'FLOAT DEFAULT 0',
        },
        'users': {
            'generated_at': 'TIMESTAMP',
            'revoked_at': 'TIMESTAMP',
        },
    }

    inspector = inspect(db.engine)
    with db.engine.begin() as conn:
        for table, columns in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c['name'] for c in inspector.get_columns(table)}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
                    if table == 'certificate_types' and column == 'render_mode':
                        # Gateways created before the port all used uploaded
                        # templates — keep rendering them with the overlay engine.
                        conn.execute(text(
                            "UPDATE certificate_types SET render_mode = 'overlay' "
                            "WHERE master_pdf_path IS NOT NULL AND master_pdf_path != ''"
                        ))


@login_manager.user_loader
def load_user(user_id):
    from app.models import Admin
    return Admin.query.get(int(user_id))
