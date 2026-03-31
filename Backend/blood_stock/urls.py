from django.urls import path
from . import views

urlpatterns = [
    path("hospital/blood-stock/", views.hospital_blood_stock),
    path("hospital/stock/add/", views.add_blood_stock),
    path("hospital/stock/remove/", views.remove_blood_stock),
    path("hospital/stock-history/", views.stock_history),
    path("hospital/bloodbank-stock/", views.blood_bank_stock),
    path("admin/combined-stock/", views.admin_combined_stock),
]
