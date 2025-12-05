# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("google_login/", views.google_login),
    path("google_signup/", views.google_signup),
    path("verify-code/", views.verify_code),
    path("patient_signup_manually/", views.patient_signup_manually),
    path('patient/login/', views.patient_login, name='patient_login'),
    path('patient/profile/', views.get_patient_profile),
    path('patient/profile/update/', views.update_patient_profile),
]
