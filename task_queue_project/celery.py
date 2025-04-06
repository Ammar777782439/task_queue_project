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

# Configure worker to consume from queues in priority order
app.conf.worker_prefetch_multiplier = 1  # Reduce prefetching

# Define the priority exchange
priority_exchange = Exchange('priority', type='direct')

# Create queues for each priority level
priority_queues = [
    Queue(f'priority_{i}', priority_exchange, routing_key=f'priority_{i}')
    for i in range(11)  # 0-10 priority levels
]

# Set task queues in priority order (highest first)
app.conf.task_queues = tuple(reversed(priority_queues))

# Default settings
app.conf.task_default_queue = 'priority_0'
app.conf.task_default_exchange = 'priority'
app.conf.task_default_routing_key = 'priority_0'

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
