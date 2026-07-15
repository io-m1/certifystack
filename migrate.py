import os
import sys
import re
import subprocess
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [MIGRATE] %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def _redact(url: str) -> str:
    return re.sub('(:)[^:@]+(@)', '\\1***\\2', url)


def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        log.error('DATABASE_URL is not set.')
        sys.exit(1)
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
        os.environ['DATABASE_URL'] = url
    log.info('DATABASE_URL: %s', _redact(url))
    if 'pooler.supabase.com' in url:
        log.info('✅ Using Supabase pooler endpoint (IPv4)')
    elif 'supabase.co' in url:
        log.warning('⚠️  Using DIRECT Supabase host — may fail on Railway (IPv6).')
        log.warning('    Set DATABASE_URL to the Transaction Pooler URL from:')
        log.warning('    Supabase Dashboard → Settings → Database → Connection Pooling')
    log.info('Running Alembic migrations…')
    try:
        result = subprocess.run(['python', '-m', 'alembic', 'upgrade', 'head'])
        if result.returncode != 0:
            log.error('Migrations FAILED (exit %d).', result.returncode)
            sys.exit(1)
    except FileNotFoundError:
        log.error("FATAL: 'alembic' binary not found on PATH. Verify alembic>=1.13.0 is in requirements.txt and was installed.")
        sys.exit(1)
    log.info('Migrations complete ✅')
    
    # Run post-migration DB sanitization for PNG templates and OBS course
    sanitize_coordinates()
    regenerate_obs_certificates()



def sanitize_coordinates():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        return
    log.info("Sanitizing certificate database coordinates...")
    
    obs_coords = {
        'name_x': 395.73,
        'name_y': 330.0,
        'name_w': 600.0,
        'name_h': 50,
        'name_font_size': 32,
        'name_align': 'center',
        'name_color': '#111111',
        
        'date_x': 395.73,
        'date_y': 205.0,
        'date_font_size': 12,
        'date_align': 'center',
        
        'cert_id_x': 585.0,
        'cert_id_y': 70.0,
        'cert_id_font_size': 11,
        
        'qr_x': 40,
        'qr_y': 40,
        'qr_size': 85,
        'mask_color': 'transparent'
    }
    
    import json
    
    # Try PostgreSQL first
    if url.startswith('postgresql://') or url.startswith('postgres://'):
        try:
            import psycopg2
            conn = psycopg2.connect(url)
            cur = conn.cursor()
            cur.execute(
                "UPDATE certificate_types SET overlay_coords = %s WHERE course_code = 'OBS' OR master_file_type = 'png'",
                (json.dumps(obs_coords),)
            )
            conn.commit()
            log.info(f"Successfully sanitized coordinates in PostgreSQL database! Row count: {cur.rowcount}")
            cur.close()
            conn.close()
        except Exception as e:
            log.error(f"PostgreSQL coordinates sanitization failed: {e}")
            
    # Try SQLite next (for local/testing DBs)
    elif os.path.exists("instance/test.db") or 'test.db' in url:
        try:
            import sqlite3
            conn = sqlite3.connect("instance/test.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE certificate_types SET overlay_coords = ? WHERE course_code = 'OBS' OR master_file_type = 'png'",
                (json.dumps(obs_coords),)
            )
            conn.commit()
            log.info(f"Successfully sanitized coordinates in SQLite database! Row count: {cur.rowcount}")
            cur.close()
            conn.close()
        except Exception as e:
            log.error(f"SQLite coordinates sanitization failed: {e}")


def regenerate_obs_certificates():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        return
    log.info("Starting regeneration of OBS/png certificates to fix alignment...")
    try:
        # Prevent starting background loops/tasks during migrations
        os.environ['START_IN_APP_WORKER'] = 'False'
        
        from app import create_app, db
        from app.models import User, Certificate, CertificateType, OrgSettings
        from app.engine.pdf_processor import generate_personalized_pdf
        from app.domain.certificates.service import resolve_certificate_asset
        import hashlib
        from datetime import datetime
        
        app = create_app()
        with app.app_context():
            cts = CertificateType.query.filter(
                (CertificateType.course_code == 'OBS') | 
                (CertificateType.master_file_type == 'png')
            ).all()
            
            for ct in cts:
                log.info(f"Regenerating for CertificateType ID={ct.id}, Name={ct.name}, Course={ct.course_code}")
                users = User.query.filter(User.certificate_type_id == ct.id).all()
                for user in users:
                    if not user.certificate_id:
                        continue
                    
                    cert = Certificate.query.get(user.certificate_id)
                    if not cert:
                        continue
                        
                    log.info(f"  Regenerating PDF for User {user.full_name} ({user.certificate_id})...")
                    try:
                        template_binary = resolve_certificate_asset(ct)
                        
                        issue_date = user.approved_at.strftime('%d %B %Y') if user.approved_at else datetime.utcnow().strftime('%d %B %Y')
                        
                        org = OrgSettings.query.first() or OrgSettings()
                        base_url = (org.verify_base_url or '').rstrip('/')
                        verify_url = f"{base_url}/verify/{user.certificate_id}" if base_url else ''
                        
                        pdf_bytes = generate_personalized_pdf(
                            template_binary,
                            overlay_coords=ct.overlay_coords,
                            full_name=user.full_name,
                            certificate_id=user.certificate_id,
                            issuance_date=issue_date,
                            include_qr=user.include_qr,
                            cert_name=ct.name,
                            master_file_type=ct.master_file_type or 'png',
                            verify_url=verify_url
                        )
                        
                        if pdf_bytes and len(pdf_bytes) > 0:
                            pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
                            cert.pdf_artifact = pdf_bytes
                            cert.pdf_hash = pdf_hash
                            db.session.commit()
                            log.info(f"  Successfully updated PDF in DB for {user.certificate_id}!")
                            
                            # Also delete from local disk archive so the new one is loaded
                            archive_path = os.path.abspath(os.path.join('archive', f"{user.certificate_id}.pdf"))
                            if os.path.exists(archive_path):
                                os.remove(archive_path)
                                log.info(f"  Cleared local disk cache at {archive_path}")
                        else:
                            log.error(f"  Generated PDF was empty for {user.certificate_id}")
                    except Exception as ex:
                        log.error(f"  Failed to regenerate certificate for {user.certificate_id}: {ex}", exc_info=True)
                        
    except Exception as e:
        log.error(f"Regeneration script initialization failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
