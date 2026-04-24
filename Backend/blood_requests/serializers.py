from rest_framework import serializers
from .models import BloodRequest
from donor.models import DonationConfirmation


class BloodRequestSerializer(serializers.ModelSerializer):
    hospital_doc = serializers.FileField(required=True)
    doctor_note  = serializers.FileField(required=False, allow_null=True)  # ← optional

    hospital_location    = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_hospital  = serializers.PrimaryKeyRelatedField(read_only=True)

    patient_confirmed_at = serializers.SerializerMethodField()
    donor_confirmed_at   = serializers.SerializerMethodField()
    donated_at           = serializers.SerializerMethodField()
    hospital_name = serializers.SerializerMethodField()
    units_required = serializers.IntegerField(required=False, default=1, min_value=1)

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "blood_type",
            "units_required",
            "urgency",
            "district",
            "hospital_name",
            "created_by_hospital",
            "hospital_location",
            "required_date",
            "reason",
            "contact_name",
            "contact_phone",
            "hospital_doc",
            "doctor_note",
            "status",
            "created_at",
            "donation_date",
            "patient_confirmed_at",
            "donor_confirmed_at",
            "donated_at",
        ]
        # ✅ These fields must not be required on input
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "donation_date",
            "hospital_location",
            "created_by_hospital",
        ]
        class Meta:
            model = BloodRequest
            fields = [...]
            read_only_fields = [...]
            extra_kwargs = {
    'reason':         {'required': False, 'allow_blank': True, 'allow_null': True},
    'required_date':  {'required': False, 'allow_null': True},
    'units_required': {'required': False},
}

    def get_patient_confirmed_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj, patient_confirmed=True
        ).first()
        return confirmation.created_at if confirmation else None

    def get_donor_confirmed_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj, donor_confirmed=True
        ).first()
        return confirmation.donation_date if confirmation else None

    def get_donated_at(self, obj):
        confirmation = DonationConfirmation.objects.filter(
            request=obj, donor_confirmed=True
        ).first()
        return confirmation.donation_date if confirmation else None
    def get_hospital_name(self, obj):
        return obj.hospital_location.name if obj.hospital_location else None