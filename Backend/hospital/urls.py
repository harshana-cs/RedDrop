from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.hospital_login),
    # path("create/", views.admin_create_hospital),
#     # path("list/", views.admin_list_hospitals),
#     path("<int:hospital_id>/reset-password/", views.admin_reset_hospital_password),
#     path("<int:hospital_id>/toggle/", views.admin_toggle_hospital),
 ]
