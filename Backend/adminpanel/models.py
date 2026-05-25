from django.db import models
from django.contrib.auth.models import User

from blood_requests.models import BloodRequest
class DonationCamp(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    hospital_name = models.CharField(max_length=200)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200)
    is_urgent = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    map_link = models.URLField(max_length=500, blank=True, null=True)
    # ── New document field ──────────────────────────────────
    authorization_letter = models.FileField(
        upload_to='camp_documents/',
        blank=True,
        null=True,
        help_text="Official authorization letter or permission document (PDF/JPG/PNG, max 5MB)"
    )

    def __str__(self):
        return self.title

from django.db import models
from hospital.models import Hospital


class Notification(models.Model):

    TYPE_CHOICES = [
        ("alert", "Alert"),
        ("system_alert", "System Alert"),
        ("camp", "Camp"),
        ("blood_request", "Blood Request"),
        ("blood_request_approved_by_admin", "Blood Request Approved by Admin"),
        ("blood_request_rejected_by_admin", "Blood Request Rejected by Admin"),
        ("blood_request_failed", "Blood Request Failed"),
        ("blood_bank_found", "Blood Bank Found"),
        ("follow_up_24h", "24h Follow-up"),
        ("donor_registration", "Donor Registration"),
        ("hospital_registration", "Hospital Registration"),
        ("blood_request_approved", "Blood Request Approved"),
        ("donor_request", "Donor Request"),
        ("donor_accept", "Donor Accepted"),
        ("donor_request_rejected", "Donor Declined"),
        ("request_completed", "Request Completed"),
        ("donation_eligibility_reminder", "Donation Eligibility Reminder"),
        ("day_before_request_confirm", "Day-Before Request Confirmation"),
    ]

    title = models.CharField(max_length=255)
    message = models.TextField()

    type = models.CharField(max_length=50, choices=TYPE_CHOICES)

    # WHO receives the notification
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True
    )

    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True
    )

    blood_request = models.ForeignKey(
        BloodRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
class HospitalAuditLog(models.Model):

    ACTION_TYPES = [
        ("login", "Hospital Login"),
        ("blood_request_create", "Blood Request Created"),
        ("stock_add", "Blood Stock Added"),
        ("stock_remove", "Blood Stock Removed"),
        ("inventory_update", "Inventory Updated"),
        ("document_upload", "Document Uploaded"),
    ]

    hospital = models.ForeignKey(
        "hospital.Hospital",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    action = models.CharField(max_length=50, choices=ACTION_TYPES)

    description = models.TextField()

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.hospital:
            return f"{self.hospital.name} - {self.action}"
        return f"System Log - {self.action}"
    
"""
=======================================================================
LOCATION 2: adminpanel/models.py — ADD THESE TWO NEW MODELS
=======================================================================
Paste the two classes below at the BOTTOM of your existing
adminpanel/models.py file (after all your current models).

Then run:
    python manage.py makemigrations
    python manage.py migrate
=======================================================================
"""

from django.db import models
from blood_requests.models import BloodRequest
from register_donor.models import Donor
from hospital.models import Hospital


class NotificationLog(models.Model):
    """Track all notifications sent for auditing"""

    TIER_CHOICES = [
        ('tier_1', 'Tier 1 (0-5km)'),
        ('tier_2', 'Tier 2 (5-15km)'),
        ('tier_3', 'Tier 3 (15-30km)'),
        ('tier_4', 'Tier 4 (30km+)'),
    ]

    blood_request = models.ForeignKey(
        BloodRequest,
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    tier = models.CharField(max_length=10, choices=TIER_CHOICES)
    distance_km = models.FloatField()
    notification_type = models.CharField(
        max_length=20,
        choices=[
            ('sms', 'SMS'),
            ('email', 'Email'),
        ]
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('sent', 'Sent'),
            ('failed', 'Failed'),
        ],
        default='sent'
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"[{self.tier}] {self.notification_type} → {self.donor.email if self.donor else 'System'} ({self.status})"


class BloodRequestEscalation(models.Model):
    """Track escalation timeline for each blood request"""

    blood_request = models.OneToOneField(
        BloodRequest,
        on_delete=models.CASCADE,
        related_name='escalation'
    )
    hospital = models.ForeignKey(
        Hospital,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Tier 1: 0–5 km
    tier_1_started = models.DateTimeField(null=True, blank=True)
    tier_1_completed = models.DateTimeField(null=True, blank=True)
    tier_1_donor_count = models.IntegerField(default=0)

    # Tier 2: 5–15 km
    tier_2_started = models.DateTimeField(null=True, blank=True)
    tier_2_completed = models.DateTimeField(null=True, blank=True)
    tier_2_donor_count = models.IntegerField(default=0)

    # Tier 3: 15–30 km
    tier_3_started = models.DateTimeField(null=True, blank=True)
    tier_3_completed = models.DateTimeField(null=True, blank=True)
    tier_3_donor_count = models.IntegerField(default=0)

    # Tier 4: 30 km+
    tier_4_started = models.DateTimeField(null=True, blank=True)
    tier_4_completed = models.DateTimeField(null=True, blank=True)
    tier_4_donor_count = models.IntegerField(default=0)

    # Blood bank / hospital stock check
    blood_bank_checked = models.DateTimeField(null=True, blank=True)
    blood_bank_stock_found = models.BooleanField(default=False)
    blood_bank_units = models.IntegerField(default=0)

    hospital_stock_checked = models.DateTimeField(null=True, blank=True)
    hospital_stock_found = models.BooleanField(default=False)
    hospital_stock_details = models.JSONField(default=dict, blank=True)

    # Overall
    completed_at = models.DateTimeField(null=True, blank=True)
    total_donors_alerted = models.IntegerField(default=0)
    success = models.BooleanField(default=False)

    def __str__(self):
        return f"Escalation for Request #{self.blood_request_id}"
