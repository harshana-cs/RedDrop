# =======================================================================
# your_project/celery.py   (LOCATION 4)
# =======================================================================
# Place this file at:  your_project/celery.py
# (same folder as settings.py and __init__.py)
# =======================================================================

import os
from celery import Celery

# Tell Celery which Django settings module to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')

app = Celery('your_project')

# Pull Celery config from Django settings, using the CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')