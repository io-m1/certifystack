from app.registry.tasks import register_task
from app import worker

def bootstrap_tasks():
    register_task("generate_certificate", worker.generate_certificate)
    register_task("dispatch_certificate", worker.dispatch_certificate)
    register_task("process_campaign", worker.process_campaign)
    register_task("process_bulk_certificates", worker.process_bulk_certificates)
    register_task("send_nudge_email", worker.send_nudge_email)
