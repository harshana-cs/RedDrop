from rest_framework import serializers
from .models import BloodRequest
from donor.models import DonationConfirmation


class BloodRequestSerializer(serializers.ModelSerializer):
    hospital_doc = serializers.FileField(required=True)
    doctor_note = serializers.FileField(required=True)

    # ✅ NEW FIELDS
    patient_confirmed_at = serializers.SerializerMethodField()
    donor_confirmed_at = serializers.SerializerMethodField()
    donated_at = serializers.SerializerMethodField()

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "blood_type",
            "units_required",
            "urgency",
            "district",
            "hospital",
            "required_date",

            # patient info
            "reason",
            "contact_name",
            "contact_phone",

            # files
            "hospital_doc",
            "doctor_note",

            # system
            "status",
            "created_at",
            "donation_date",

            # ✅ NEW
            "patient_confirmed_at",
            "donor_confirmed_at",
            "donated_at",
        ]

    def get_patient_confirmed_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj,
            patient_confirmed=True
        ).first()
        return confirmation.created_at if confirmation else None

    def get_donor_confirmed_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj,
            donor_confirmed=True
        ).first()
        return confirmation.donation_date if confirmation else None

    def get_donated_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj,
            donor_confirmed=True
        ).first()
        return confirmation.donation_date if confirmation else None
