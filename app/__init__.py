from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__, static_folder='../static')
    app.config.from_object('app.config.Config')

    db.init_app(app)
    
    uploads_dir = os.path.join(os.path.abspath(os.path.dirname(app.root_path)), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)
    
    with app.app_context():
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            from sqlalchemy import event
            @event.listens_for(db.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()


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


from app.models import Admin


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))
