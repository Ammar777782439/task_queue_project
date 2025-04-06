
from django.db import models

class Job(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    task_name = models.CharField(max_length=255)
    priority = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    last_attempt_time = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.task_name} - {self.status}"
