# Asynchronous Task Queue Project

This project implements an asynchronous task queue using Django, Celery, Redis, and PostgreSQL.

## Features

*   **Job Persistence:** Jobs are stored in a PostgreSQL database.
*   **Retry Mechanism:** Failed tasks are automatically retried with exponential backoff.
*   **Job Prioritization:** Tasks can be assigned priorities (requires broker support).
*   **Concurrency Control:** Celery worker concurrency can be configured.
*   **Job Status Tracking:** Job status (pending, in\_progress, completed, failed) is tracked in the database.
*   **Failure Handling:** Basic failure handling logs errors and updates status. Further actions (alerting, dead-letter queue) can be added.
*   **Web Interface:** A simple web form to create and queue new jobs.

## Setup and Running

**Prerequisites:**

*   Python 3.x
*   PostgreSQL server running and accessible.
*   Docker and Docker Compose (for running Redis).
*   A Python virtual environment tool (like `venv`).

**Setup Steps:**

1.  **Clone the repository (if applicable) or ensure you are in the project directory.**

2.  **Create and activate a Python virtual environment:**
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    # source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Database:**
    *   Ensure your PostgreSQL server is running.
    *   Create a database named `task_queue_db` (or update `DATABASES` in `task_queue_project/settings.py` with your database details: NAME, USER, PASSWORD, HOST, PORT).

5.  **Apply Database Migrations:**
    ```bash
    python manage.py makemigrations jobs
    python manage.py migrate
    ```

6.  **Create a Django Superuser (for admin access):**
    ```bash
    python manage.py createsuperuser
    ```

**Running the Services:**

You need to run the following components, preferably in separate terminal windows/tabs:

1.  **Start Redis using Docker Compose:**
    ```bash
    docker-compose up -d redis
    ```
    *(Note: This exposes Redis on port 16379 as configured in `docker-compose.yml` and `settings.py`)*

2.  **Start the Celery Worker with Priority Support:**
    *   Make sure your virtual environment is activated.
    *   Use the `solo` pool for compatibility on Windows and specify the queue:
        ```bash
        celery -A task_queue_project worker --loglevel=info -P solo -Q jobs
        ```
    *   *(Optional) For concurrency on non-Windows or using gevent/eventlet:*
        ```bash
        # Example with 4 concurrent workers (prefork pool - may have issues on Windows)
        # celery -A task_queue_project worker --loglevel=info -c 4 -Q jobs
        # Example with gevent (requires pip install gevent)
        # celery -A task_queue_project worker --loglevel=info -P gevent -c 100 -Q jobs
        ```
    *   **Note:** The `-Q jobs` parameter is important to ensure the worker consumes from the priority-enabled queue.

3.  **Start Celery Beat (for scheduled tasks):**
    *   Make sure your virtual environment is activated.
    *   In a **separate terminal** from the worker:
        ```bash
        celery -A task_queue_project beat --loglevel=info
        ```
    *   *(Note: This command starts Celery Beat using the default scheduler. It will pick up tasks scheduled with a specific time (`eta`) but does not support managing periodic tasks via the Django admin, which requires installing `django-celery-beat`.)*

4.  **Start the Django Development Server:**
    *   Make sure your virtual environment is activated.
    ```bash
    python manage.py runserver
    ```

**Accessing the Application:**

*   **Web Interface (Create Job):** `http://127.0.0.1:8000/jobs/create/`
*   **Django Admin Interface:** `http://127.0.0.1:8000/admin/` (Log in with your superuser credentials to view and manage jobs).

## Creating Jobs

*   **Via Web Interface:** Navigate to `http://127.0.0.1:8000/jobs/create/`, fill in the form (optionally set a future "Scheduled Time"), and click "Create Job".
*   **Via Management Command:**
    ```bash
    # Immediate execution
    python manage.py create_job "Immediate Task" --priority 5 --max_retries 2

    # Scheduled execution (Requires Celery Beat to be running)
    python manage.py create_job "Scheduled Task" --schedule_at "2025-04-07 10:30:00"
    ```

## Monitoring

*   Check the output of the Celery worker terminal for task processing logs.
*   Monitor job statuses via the Django Admin interface (`/admin/jobs/job/`).

## Priority Support

*   Tasks are executed based on their priority level (higher values = higher priority).
*   When creating a job, set the priority field to a value between 0-10 (default is 0).
*   The priority system requires Redis as the broker and the worker must be started with the `-Q jobs` parameter.
*   Tasks with the same priority are executed in FIFO (First In, First Out) order.
*   Priority only affects tasks that are already in the queue - it doesn't preempt currently running tasks.
