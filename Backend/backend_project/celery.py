# =======================================================================
# your_project/celery.py   (LOCATION 4)
# =======================================================================
# Place this file at:  your_project/celery.py
# (same folder as settings.py and __init__.py)
# =======================================================================

import os

from celery import Celery

# Tell Celery which Django settings module to use
# Must match `manage.py` / project package name.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend_project.settings")

app = Celery("backend_project")

# Pull Celery config from Django settings, using the CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Ensure project-level tasks module is imported so Celery registers the tasks.
# (This repo keeps Celery tasks in `Backend/celery_task.py`, not inside an app.)
try:
    import celery_task  # noqa: F401
except Exception:
    # Non-fatal: allows Django to start even when Celery deps/broker aren't set up.
    pass


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
