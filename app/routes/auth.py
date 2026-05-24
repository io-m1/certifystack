from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required
from app.models import Admin
from app import db
import os
bp = Blueprint('auth', __name__)
HARDCODED_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
HARDCODED_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin').strip().lower()
HARDCODED_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    import traceback
    try:
        if request.method == 'POST':
            identifier = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            is_hardcoded = identifier in (HARDCODED_USERNAME.lower(), HARDCODED_EMAIL.lower()
                                          ) and password == HARDCODED_PASSWORD
            if is_hardcoded:
                admin = Admin.query.filter_by(email=HARDCODED_EMAIL).first()
                if not admin:
                    admin = Admin(email=HARDCODED_EMAIL)
                    admin.set_password(HARDCODED_PASSWORD)
                    db.session.add(admin)
                    db.session.commit()
                login_user(admin)
                return redirect(url_for('certificates.dashboard'))
            admin = Admin.query.filter(db.or_(
                Admin.email == identifier,
                Admin.email == (identifier.split('@')[0] if '@' not in identifier else identifier)
            )).first()
            if admin and admin.check_password(password):
                login_user(admin)
                return redirect(url_for('certificates.dashboard'))
            flash('Invalid credentials')
        return render_template('login.html')
    except Exception as e:
        print("====== AUTH CRASH ======")
        traceback.print_exc()
        return jsonify({"error": "crash", "traceback": traceback.format_exc()}), 500


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/admin/setup', methods=['GET', 'POST'])
def emergency_setup():
    setup_key = os.environ.get('SETUP_KEY', '')
    if request.method == 'POST':
        provided_key = request.form.get('setup_key', '')
        if not setup_key or provided_key != setup_key:
            return (jsonify({'error': 'Invalid setup key'}), 403)
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not email or not password:
            return (jsonify({'error': 'Email and password required'}), 400)
        admin = Admin.query.filter_by(email=email).first()
        if admin:
            admin.set_password(password)
            db.session.commit()
            return jsonify({'message': f'Password updated for {email}'})
        else:
            admin = Admin(email=email)
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            return jsonify({'message': f'Admin created: {email}'})
    return '\n    <html><body style="font-family:sans-serif;max-width:400px;margin:60px auto;padding:20px">\n    <h2>CertifyStack Setup</h2>\n    <form method="POST">\n        <p><input name="setup_key" type="password" placeholder="Setup Key (SETUP_KEY env var)" style="width:100%;padding:8px;margin-bottom:10px"></p>\n        <p><input name="email" type="email" placeholder="Admin Email" style="width:100%;padding:8px;margin-bottom:10px"></p>\n        <p><input name="password" type="password" placeholder="Admin Password" style="width:100%;padding:8px;margin-bottom:10px"></p>\n        <button type="submit" style="width:100%;padding:10px;background:#1a1a2e;color:white;border:none;cursor:pointer">Create / Reset Admin</button>\n    </form>\n    </body></html>\n    '
