import hashlib
import json
import uuid
import hmac
from datetime import datetime
from flask import current_app
from app.models import db, CertificateLedgerEntry

def get_server_secret():
    # Fallback for dev if not set
    return current_app.config.get('SECRET_KEY', 'default-clp-secret').encode('utf-8')

def compute_entry_hash(cert_id, event_type, payload, prev_hash, timestamp_str):
    payload_str = json.dumps(payload, sort_keys=True) if payload else "{}"
    raw = f"{cert_id}|{event_type}|{payload_str}|{prev_hash}|{timestamp_str}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def compute_signature(entry_hash):
    secret = get_server_secret()
    return hmac.new(secret, entry_hash.encode('utf-8'), hashlib.sha256).hexdigest()

def append_ledger_event(cert_id, event_type, payload=None):
    """
    Appends an immutable, cryptographically verifiable event to the CLP ledger.
    """
    if payload is None:
        payload = {}

    last = CertificateLedgerEntry.query.filter_by(cert_id=cert_id).order_by(CertificateLedgerEntry.created_at.desc(), CertificateLedgerEntry.id.desc()).first()
    prev_hash = last.entry_hash if last else "GENESIS"

    now = datetime.utcnow()
    timestamp_str = now.isoformat()

    entry_hash = compute_entry_hash(cert_id, event_type, payload, prev_hash, timestamp_str)
    signature = compute_signature(entry_hash)

    entry = CertificateLedgerEntry(
        id=str(uuid.uuid4()),
        cert_id=cert_id,
        event_type=event_type,
        payload=payload,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=now,
        signature=signature
    )

    db.session.add(entry)
    db.session.flush() # ensure it's in the session
    return entry

def verify_hash_chain(chain):
    """
    Verifies the cryptographic integrity of the entire event chain.
    """
    if not chain:
        return True

    for i in range(len(chain)):
        entry = chain[i]
        prev_hash = chain[i-1].entry_hash if i > 0 else "GENESIS"
        
        # Check linkage
        if entry.prev_hash != prev_hash:
            return False
            
        # Check hash content
        timestamp_str = entry.created_at.isoformat()
        expected_hash = compute_entry_hash(entry.cert_id, entry.event_type, entry.payload, prev_hash, timestamp_str)
        if entry.entry_hash != expected_hash:
            return False
            
        # Check server signature (tamper-evident against DB admins)
        expected_sig = compute_signature(entry.entry_hash)
        if entry.signature != expected_sig:
            return False

    return True

def reduce_events(chain):
    """
    Deterministically rebuilds the certificate state strictly from the ledger.
    """
    class ReconstructedState:
        def __init__(self):
            self.state = "UNKNOWN"
            self.pdf_hash = None
            self.sendgrid_id = None
            self.failure_count = 0
            self.last_error = None
            
    reconstructed = ReconstructedState()
    
    for entry in chain:
        if entry.event_type == "CERT_CREATED":
            reconstructed.state = "DRAFT"
        elif entry.event_type == "APPROVED":
            reconstructed.state = "APPROVED_FOR_GENERATION"
        elif entry.event_type == "GENERATION_STARTED":
            reconstructed.state = "GENERATING"
        elif entry.event_type == "GENERATION_COMPLETED":
            reconstructed.state = "GENERATED"
            reconstructed.pdf_hash = entry.payload.get('pdf_hash')
        elif entry.event_type == "READY_FOR_DISPATCH":
            reconstructed.state = "READY_FOR_DISPATCH"
        elif entry.event_type == "QUEUED":
            reconstructed.state = "QUEUED_FOR_DISPATCH"
        elif entry.event_type == "DISPATCH_STARTED":
            reconstructed.state = "DISPATCHING"
        elif entry.event_type == "DISPATCH_CONFIRMED":
            reconstructed.state = "SENT"
            reconstructed.sendgrid_id = entry.payload.get('message_id')
        elif entry.event_type == "GENERATION_FAILED":
            reconstructed.failure_count += 1
            reconstructed.last_error = entry.payload.get('error')
            reconstructed.state = "FAILED_GENERATION" if reconstructed.failure_count < 5 else "PERMANENTLY_FAILED"
        elif entry.event_type == "DISPATCH_FAILED":
            reconstructed.failure_count += 1
            reconstructed.last_error = entry.payload.get('error')
            reconstructed.state = "FAILED_DISPATCH" if reconstructed.failure_count < 5 else "PERMANENTLY_FAILED"
            
    return reconstructed

def resolve_truth(cert_id):
    """
    The CLP Truth Engine Resolver. Never trusts the DB state, only the ledger.
    """
    from app.models import Certificate
    cert = Certificate.query.get(cert_id)
    
    chain = CertificateLedgerEntry.query.filter_by(cert_id=cert_id).order_by(CertificateLedgerEntry.created_at.asc(), CertificateLedgerEntry.id.asc()).all()
    
    if not chain:
        return {
            "stored_state": cert.status if cert else "NOT_FOUND",
            "derived_state": "NO_LEDGER_FOUND",
            "integrity": "INVALID"
        }

    if not verify_hash_chain(chain):
        return {
            "stored_state": cert.status if cert else "NOT_FOUND",
            "derived_state": "LEDGER_TAMPERED",
            "integrity": "INVALID"
        }

    reconstructed = reduce_events(chain)
    
    is_valid = False
    if cert:
        # Check if derived state matches stored state
        state_match = (cert.status == reconstructed.state)
        hash_match = (cert.pdf_hash == reconstructed.pdf_hash)
        sendgrid_match = (cert.sendgrid_message_id == reconstructed.sendgrid_id)
        is_valid = state_match and hash_match and sendgrid_match

    return {
        "stored_state": cert.status if cert else "NOT_FOUND",
        "derived_state": reconstructed.state,
        "pdf_hash": reconstructed.pdf_hash,
        "sendgrid_id": reconstructed.sendgrid_id,
        "integrity": "VALID" if is_valid else "STATE_DRIFT_DETECTED",
        "events": [{"type": e.event_type, "time": e.created_at.isoformat(), "hash": e.entry_hash} for e in chain]
    }
