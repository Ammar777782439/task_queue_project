from django.contrib import admin
from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_name', 'status', 'priority', 'retry_count', 'created_at', 'last_attempt_time')
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('id', 'task_name', 'status')
    ordering = ('-created_at',)
    readonly_fields = ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at')
    list_per_page = 25

    fieldsets = (
        (None, {
            'fields': ('task_name', 'priority', 'max_retries', 'scheduled_time')
        }),
        ('Status & Tracking', {
            'fields': ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at'),
            'classes': ('collapse',) # Keep this section collapsed by default
        }),
    )
