from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_donor, name="register_donor"),
    path("login-success/", views.login_success, name="login_success"),


]
