from django.urls import path
from .views import (
    admin_all_hospitals_stock,
    admin_hospital_stock,
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
    admin_user_detail,
    api_blood_type_distribution,
    api_request_status_overview,
    hospital_request_detail,
    approve_hospital_request,
    reject_hospital_request,
    get_notifications,
    admin_hospital_audit_logs,
    mark_notification_read,
    admin_users,
    admin_blood_inventory,
    admin_add_inventory,
    admin_remove_inventory,
    admin_bulk_add_inventory,
    admin_stock_movements,
    admin_activity_logs,

    # ✅ Donation Camps
    admin_donation_camps,
    admin_donation_camp_detail,
    public_donation_camps,
)

urlpatterns = [
    path("secret-login/", admin_secret_login),

    # ── Blood Requests ─────────────────────────────────────────
    path("pending-blood-requests/",                    admin_pending_blood_requests),
    path("blood-request/<int:request_id>/approve/",    admin_approve_blood_request),
    path("blood-request/<int:request_id>/reject/",     admin_reject_blood_request),
    path("blood-requests/processed/",                  admin_processed_blood_requests),

    # ── Donors ────────────────────────────────────────────────
    path("pending-donor-registrations/",               admin_pending_donor_registrations),
    path("donor/<int:donor_id>/approve/",              admin_approve_donor_registration),
    path("donor/<int:donor_id>/reject/",               admin_reject_donor_registration),
    path("donors/processed/",                          admin_processed_donor_registrations),

    # ── Hospitals (manual creation) ───────────────────────────
    path("hospital/create/",                           admin_create_hospital),
    path("hospitals/list/",                            admin_list_hospitals),
    path("hospital/<int:hospital_id>/reset-password/", admin_reset_hospital_password),
    path("hospital/<int:hospital_id>/toggle/",         admin_toggle_hospital),
    path("hospital-stock/",                            admin_hospital_stock),

    # ── Hospital Applications ─────────────────────────────────
    path("hospital-requests/",                         admin_hospital_requests),
    path("hospital-request/<int:pk>/",                 hospital_request_detail),
    path("hospital-request/<int:pk>/approve/",         approve_hospital_request),
    path("hospital-request/<int:pk>/reject/",          reject_hospital_request),
    path("hospital-audit-logs/",                       admin_hospital_audit_logs),

    # ── Analytics ─────────────────────────────────────────────
    path("analytics/blood-types/",                     api_blood_type_distribution),
    path("analytics/request-status/",                  api_request_status_overview),

    # ── Notifications (mark-all-read BEFORE <int:id> route) ───
    path("notifications/mark-all-read/",               mark_notification_read),
    path("notifications/<int:notification_id>/read/",  mark_notification_read),
    path("notifications/",                             get_notifications),

    # ── Users ─────────────────────────────────────────────────
    path("users/",                                     admin_users),
    path("users/<int:user_id>/",                       admin_user_detail),

    # ── Blood Inventory ───────────────────────────────────────
    path("blood-inventory/",                           admin_blood_inventory),
    path("inventory/add/",                             admin_add_inventory),
    path("inventory/remove/",                          admin_remove_inventory),
    path("inventory/bulk-add/",                        admin_bulk_add_inventory),
    path("stock-movements/",                           admin_stock_movements),
    path('combined-stock/', admin_all_hospitals_stock),

    # ── Audit Logs ────────────────────────────────────────────
    path("activity-logs/",                             admin_activity_logs),

    # ── Donation Camps (admin) ────────────────────────────────
    path("donation-camps/",                            admin_donation_camps),
    path("donation-camps/<int:camp_id>/",              admin_donation_camp_detail),

]