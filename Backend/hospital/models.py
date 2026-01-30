from django.db import models
from django.contrib.auth.hashers import make_password, check_password

class Hospital(models.Model):
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.name
class HospitalProfile(models.Model):
    hospital = models.OneToOneField(
        Hospital,
        on_delete=models.CASCADE,
        related_name="blood_request"
    )

    district = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20)
    registration_number = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hospital.name} Profile"
