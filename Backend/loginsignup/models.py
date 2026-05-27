from django.db import models
from django.contrib.auth.hashers import make_password, check_password as django_check_password


# -------------------------------------------------
# GOOGLE SIGNUP (ONLY FOR VERIFICATION)
# -------------------------------------------------
class GoogleSignup(models.Model):
    email              = models.EmailField(unique=True)
    fullname           = models.CharField(max_length=200)
    verification_code  = models.CharField(max_length=6, blank=True)
    is_verified        = models.BooleanField(default=False)
    pending_password   = models.CharField(max_length=200, blank=True, null=True)  # ← new
    created_at         = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


# -------------------------------------------------
# PATIENT = BASE USER (LOGIN IDENTITY)
# -------------------------------------------------
class Patient(models.Model):
    fullname = models.CharField(max_length=100)
    emailaddress = models.EmailField(unique=True)

    password = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_on = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    # AFTER
def check_password(self, raw_password):
    if not self.password:   # ← this line added
        return False
    return django_check_password(raw_password, self.password)

    def __str__(self):
        return self.emailaddress

