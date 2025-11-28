from django.contrib import admin
from .models import GoogleSignup

@admin.register(GoogleSignup)
class GoogleSignupAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'user_type', 'is_verified', 'created_on')
    search_fields = ('email', 'user_type')
    list_filter = ('user_type', 'is_verified', 'created_on')
