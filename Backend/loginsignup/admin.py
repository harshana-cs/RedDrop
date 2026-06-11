from django.contrib import admin
from .models import GoogleSignup, Patient


@admin.register(GoogleSignup)
class GoogleSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "fullname", "is_verified", "created_on")
    list_filter = ("is_verified",)
    search_fields = ("email", "fullname")
    list_display = ['email', 'fullname', 'is_verified', 'created_at']


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("emailaddress", "fullname", "created_on")
    search_fields = ("emailaddress", "fullname")


# @admin.register(Donor)
# class DonorAdmin(admin.ModelAdmin):
#     list_display = ("patient", "created_on")
