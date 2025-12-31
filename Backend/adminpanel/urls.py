from django.urls import path
from .views import admin_secret_login

urlpatterns = [
    path("secret-login/", admin_secret_login),
]
