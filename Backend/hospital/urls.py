from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.hospital_login),
    path("register/", views.hospital_register),

    path("profile/", views.hospital_profile),
    path("dashboard/", views.hospital_dashboard),
    path("blood-requests/", views.hospital_blood_requests),
    path("blood-stock/", views.hospital_blood_stock),
    path("donors/", views.hospital_donors),
    path("stock-history/", views.hospital_stock_history),
    path("blood-request/create/", views.hospital_create_blood_request),
    path("notifications/", views.hospital_notifications),
    path(
    "request/<int:request_id>/donors/",
    views.hospital_request_donors
),
path(
    "notifications/<int:notification_id>/read/",
    views.mark_notification_read
),
path(
    "notifications/mark-all-read/",
    views.mark_all_notifications_read
),
path(
    "request/<int:request_id>/escalation-status/",
    views.hospital_request_escalation_status
),
    
]
