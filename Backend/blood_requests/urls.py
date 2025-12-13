from django.urls import path
from . import views

urlpatterns = [
    # Page served by Django (JS-based submission)
    path("create/", views.create_request_view, name="blood_request_create"),

    # Optional: list page
    path("list/", views.request_list, name="blood_request_list"),

    # API endpoint
    path("api/create/", views.api_create_request, name="api_create_request"),
]
