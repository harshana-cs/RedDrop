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
]
