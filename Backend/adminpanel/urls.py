from django.urls import path
from .views import (
    admin_secret_login,

    admin_pending_blood_requests,
    admin_approve_blood_request,
    admin_reject_blood_request,

    admin_pending_donor_registrations,
    admin_approve_donor_registration,
    admin_reject_donor_registration,

    admin_reset_hospital_password,
    admin_list_hospitals,
    admin_toggle_hospital,
    admin_create_hospital,

    admin_processed_blood_requests,
    admin_processed_donor_registrations,

    admin_hospital_requests,
    api_blood_type_distribution,
    api_request_status_overview,
    hospital_request_detail,        # ✅ ADD THIS
    approve_hospital_request,
    reject_hospital_request,
)

urlpatterns = [
    path("secret-login/", admin_secret_login),

    # Blood
    path("pending-blood-requests/", admin_pending_blood_requests),
    path("blood-request/<int:request_id>/approve/", admin_approve_blood_request),
    path("blood-request/<int:request_id>/reject/", admin_reject_blood_request),

    # Donors
    path("pending-donor-registrations/", admin_pending_donor_registrations),
    path("donor/<int:donor_id>/approve/", admin_approve_donor_registration),
    path("donor/<int:donor_id>/reject/", admin_reject_donor_registration),

    # Hospitals (manual)
    path("hospital/create/", admin_create_hospital),
    path("hospitals/list/", admin_list_hospitals),
    path("hospital/<int:hospital_id>/reset-password/", admin_reset_hospital_password),
    path("hospital/<int:hospital_id>/toggle/", admin_toggle_hospital),

    # Processed
    path("blood-requests/processed/", admin_processed_blood_requests),
    path("donors/processed/", admin_processed_donor_registrations),

    # Hospital applications (IMPORTANT)
    path("hospital-requests/", admin_hospital_requests),                 
    path("hospital-request/<int:pk>/", hospital_request_detail),        
    path("hospital-request/<int:pk>/approve/", approve_hospital_request),
    path("hospital-request/<int:pk>/reject/", reject_hospital_request),
    # adminpanel/urls.py
path("analytics/blood-types/", api_blood_type_distribution),
path("analytics/request-status/", api_request_status_overview),

]
