import logging
import threading
from flask import current_app
logger = logging.getLogger(__name__)


from app.registry.tasks import get_task

class TaskQueue:
    def __init__(self, app=None):
        if app:
            self.init_app(app)

    def init_app(self, app):
        app.task_queue = self
        logger.info('TaskQueue initialized (Mode: Database-Backed)')

    def enqueue(self, task_name: str, idempotency_key: str = None, **kwargs):
        # Validate the task exists before queuing
        try:
            get_task(task_name)
        except KeyError:
            raise RuntimeError(f"TASK NOT REGISTERED: {task_name}")
            
        kwargs.pop('job_timeout', None)
        
        logger.info(f'Enqueuing task to DB: {task_name} with args: {list(kwargs.keys())}')

        from app.models import db, JobQueue
        
        if idempotency_key:
            existing = JobQueue.query.filter_by(idempotency_key=idempotency_key).first()
            if existing:
                logger.info(f"Duplicate job skipped (idempotency_key={idempotency_key})")
                return existing.id
                
        job = JobQueue(
            task_name=task_name,
            payload=kwargs,
            idempotency_key=idempotency_key,
            status="PENDING"
        )
        db.session.add(job)
        db.session.commit()
        return job.id


task_queue = TaskQueue()
