from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from kombu import Exchange, Queue

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_queue_project.settings')

app = Celery('task_queue_project')

# Using a string here means the worker doesn’t have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configure concurrency settings
app.conf.worker_prefetch_multiplier = 4  # Allow each worker to prefetch 4 tasks
app.conf.worker_concurrency = 4  # Allow 4 concurrent worker processes
app.conf.worker_disable_rate_limits = True

# Define the default exchange and queue
default_exchange = Exchange('default', type='direct')
default_queue = Queue('default', default_exchange, routing_key='default')

# Set task queues
app.conf.task_queues = (default_queue,)

# Default settings
app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_routing_key = 'default'

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
