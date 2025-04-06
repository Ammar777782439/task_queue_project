from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import CreateJobForm
from .models import Job
from .tasks import process_job_task
import logging

logger = logging.getLogger(__name__)

def create_job_view(request):
    if request.method == 'POST':
        form = CreateJobForm(request.POST)
        if form.is_valid():
            task_name = form.cleaned_data['task_name']
            priority = form.cleaned_data['priority']
            max_retries = form.cleaned_data['max_retries']
            # Get any other task-specific parameters from the form here

            try:
                # Create the Job record in the database
                job = Job.objects.create(
                    task_name=task_name,
                    priority=priority,
                    max_retries=max_retries,
                    status='pending' # Initial status
                    # Add any other specific parameters to the Job model if needed
                )
                logger.info(f"Created job {job.id} via web form.")

                # Queue the job using Celery
                process_job_task.apply_async(
                    args=[job.id],
                    priority=priority,
                    retry_policy={
                        'max_retries': job.max_retries,
                    }
                    # Pass any other task-specific kwargs needed by process_job_task
                    # kwargs={'email_address': form.cleaned_data.get('email_address')}
                )
                logger.info(f"Queued job {job.id} via web form.")

                messages.success(request, f'Successfully created and queued job "{task_name}" (ID: {job.id}).')
                return redirect('create_job') # Redirect back to the same page (or a success page)

            except Exception as e:
                logger.error(f"Error creating/queuing job from web form: {e}")
                messages.error(request, f'Failed to create or queue job: {e}')
                # Optionally, render the form again with the error
                # context = {'form': form}
                # return render(request, 'jobs/create_job.html', context)

    else: # GET request
        form = CreateJobForm()

    context = {'form': form}
    return render(request, 'jobs/create_job.html', context)

# Add other views here if needed
