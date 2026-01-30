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
    admin_toggle_hospital
    , admin_create_hospital,
)

urlpatterns = [
    path("secret-login/", admin_secret_login),

    path("pending-blood-requests/", admin_pending_blood_requests),
    path("blood-request/<int:request_id>/approve/", admin_approve_blood_request),
    path("blood-request/<int:request_id>/reject/", admin_reject_blood_request),

    path("pending-donor-registrations/", admin_pending_donor_registrations),
    path("donor/<int:donor_id>/approve/", admin_approve_donor_registration),
    path("donor/<int:donor_id>/reject/", admin_reject_donor_registration),
     # ✅ HOSPITAL ADMIN MANAGEMENT
    path("hospital/create/", admin_create_hospital),
    path("hospitals/list/", admin_list_hospitals),
    path("hospital/<int:hospital_id>/reset-password/", admin_reset_hospital_password),
    path("hospital/<int:hospital_id>/toggle/", admin_toggle_hospital),

]
