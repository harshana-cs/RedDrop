from django.urls import path
from . import views

urlpatterns = [
    path("secret-login/", views.admin_secret_login),

    # Blood requests
    path("pending-blood-requests/", views.admin_pending_blood_requests),
    path("blood-request/<int:request_id>/approve/", views.admin_approve_blood_request),
    path("blood-request/<int:request_id>/reject/", views.admin_reject_blood_request),

    # Donor registrations  ✅ THIS WAS MISSING / MISMATCHED
    path("pending-donor-registrations/", views.admin_pending_donor_registrations),
    path("donor/<int:donor_id>/approve/", views.admin_approve_donor_registration),
    path("donor/<int:donor_id>/reject/", views.admin_reject_donor_registration),
]
