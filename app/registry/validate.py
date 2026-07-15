from app.registry.tasks import TASK_REGISTRY

def validate_tasks():
    required = [
        "generate_certificate",
        "dispatch_certificate",
        "process_campaign",
        "process_bulk_certificates",
        "send_nudge_email",
    ]

    missing = [t for t in required if t not in TASK_REGISTRY]

    if missing:
        raise RuntimeError(f"Missing task bindings: {missing}")
