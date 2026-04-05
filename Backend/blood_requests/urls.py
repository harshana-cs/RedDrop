from django.urls import path
from . import views

urlpatterns = [
    # ==========================
    # API – Blood Requests
    # ==========================
    path(
        "api/create/",
        views.api_create_request,
        name="api_create_request"
    ),

    path(
        "api/user_requests/",
        views.api_user_requests,
        name="api_user_requests"
    ),

    # ==========================
    # API – Patient Actions
    # ==========================
    path(
        "api/confirm-receipt/<int:request_id>/",
        views.api_patient_confirm_receipt,
        name="api_patient_confirm_receipt"
    ),

    path(
        "api/patient/approved-request/",
        views.api_patient_approved_request,
        name="api_patient_approved_request"
    ),
    path(
    "api/compatible-donors/",
    views.api_compatible_donors_for_patient,
    name="api_compatible_donors_for_patient"
),
path("api/public-requests/", views.public_blood_requests, name="api_public_blood_requests"),
path("api/patient-notifications/", views.api_patient_notifications, name="api_patient_notifications"),
path("api/request-status/<int:request_id>/", views.api_request_status, name="api_request_status"),
]
