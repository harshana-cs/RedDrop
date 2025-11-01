from django.urls import path
from . import views

urlpatterns = [
    path('patient/signup/', views.signup, name='patient_signup'),
    path('', views.signup, name='home'),  # root of loginsignup/ redirects to signup
]
