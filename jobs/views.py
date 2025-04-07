from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import CreateJobForm # We will update this form later to include scheduled_time
from .models import Job
from .tasks import process_job_task
import logging
from django.utils import timezone

from django.db import models

logger = logging.getLogger(__name__)

def create_job_view(request):
    if request.method == 'POST':
        form = CreateJobForm(request.POST)
        if form.is_valid():
            task_name = form.cleaned_data['task_name']
            priority = form.cleaned_data['priority']
            max_retries = form.cleaned_data['max_retries']
            # Get scheduled_time from the form (we'll add this field to the form next)
            scheduled_time_input = form.cleaned_data.get('scheduled_time')

            try:
                # بجيب أعلى أولوية موجودة في قاعدة البيانات قبل إنشاء المهمة الجديدة
                existing_max_priority = Job.objects.aggregate(max_priority=models.Max('priority'))['max_priority'] or 0
                
                # Create the Job record in the database
                job = Job.objects.create(
                    task_name=task_name,
                    priority=priority,
                    max_retries=max_retries,
                    status='pending', # Initial status
                    scheduled_time=scheduled_time_input # Save scheduled time
                )
                logger.info(f"Created job {job.id} via web form.")

                # Prepare Celery task arguments and options
                task_args = [job.id]
                task_kwargs = {
                    # Pass any other task-specific kwargs needed by process_job_task
                }
            
                
                # Calculate countdown based on priority (higher priority = lower countdown)
                # Max priority (10) gets 0 seconds, lowest priority (0) gets 10 seconds
                countdown = max(0, existing_max_priority - priority)

                celery_options = {
                    'priority': priority,  # Keep this for reference
                    'retry_policy': {
                        'max_retries': job.max_retries,
                    },
                    'countdown': countdown  # Add countdown based on priority
                }

                # Use 'eta' if scheduled_time is set and in the future
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    celery_options['eta'] = job.scheduled_time
                    logger.info(f"Scheduling job {job.id} for {job.scheduled_time}")
                    success_message = f'Successfully created and scheduled job "{task_name}" (ID: {job.id}) for {job.scheduled_time}.'
                else:
                    # If scheduled_time is in the past or not set, queue for immediate processing
                    if job.scheduled_time:
                         logger.warning(f"Scheduled time for job {job.id} ({job.scheduled_time}) is in the past. Queuing for immediate processing.")
                    else:
                        logger.info(f"Queuing job {job.id} for immediate processing.")
                    success_message = f'Successfully created and queued job "{task_name}" (ID: {job.id}) for immediate processing.'


                # Queue the job using Celery
                process_job_task.apply_async(
                    args=task_args,
                    kwargs=task_kwargs,
                    **celery_options
                )

                messages.success(request, success_message)
                return redirect('create_job') # Redirect back to the same page

            except Exception as e:
                logger.error(f"Error creating/queuing job from web form: {e}")
                messages.error(request, f'Failed to create or queue job: {e}')
                # Fall through to render the form again with errors

    else: # GET request
        form = CreateJobForm()

    context = {'form': form}
    return render(request, 'jobs/create_job.html', context)

# Add other views here if needed
