TASK_REGISTRY = {}

def register_task(name: str, fn):
    TASK_REGISTRY[name] = fn

def get_task(name: str):
    return TASK_REGISTRY[name]
