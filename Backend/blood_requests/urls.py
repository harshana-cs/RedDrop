from django.urls import path
from . import views

urlpatterns = [

    # ==========================
    # PAGES (Django-rendered)
    # ==========================
    path(
        "create/",
        views.create_request_view,
        name="blood_request_create"
    ),

    path(
        "list/",
        views.request_list,
        name="blood_request_list"
    ),

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
)
]
