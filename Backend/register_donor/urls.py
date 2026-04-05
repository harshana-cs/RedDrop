from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_donor, name="register_donor"),
    path("check-approval/", views.check_donor_approval, name="check_donor_approval"),
    path("api/test/", views.test_api)
]
