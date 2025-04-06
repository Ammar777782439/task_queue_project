from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_job_view, name='create_job'),
    # Add other app-specific URLs here
]
