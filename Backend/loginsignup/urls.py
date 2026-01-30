# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ---------- GOOGLE AUTH ----------
    path("google_signup/", views.google_signup, name="google_signup"),
    path("verify-code/", views.verify_code, name="verify_google_code"),
    path("google_login/", views.google_login, name="google_login"),

    # ---------- MANUAL AUTH ----------
    path("signup/", views.patient_signup_manually, name="manual_signup"),
    path("login/", views.patient_login, name="manual_login"),
    path("user-capabilities/", views.api_user_capabilities, name="api_user_capabilities"),
]
