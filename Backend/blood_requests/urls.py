from django.urls import path
from . import views

urlpatterns = [
    # Page served by Django (JS-based submission)
    path("create/", views.create_request_view, name="blood_request_create"),

    # Optional: list page
    path("list/", views.request_list, name="blood_request_list"),

    # API endpoint
    path("api/create/", views.api_create_request, name="api_create_request"),
    path('api/user_requests/', views.api_user_requests, name='api_user_requests'),
    path('api/confirm/<int:request_id>/', views.api_confirm_receipt, name='api_confirm_receipt'),
]
