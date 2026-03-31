from rest_framework import serializers
from .models import DonationCamp          # adjust import path to wherever your model lives
 
 
class DonationCampSerializer(serializers.ModelSerializer):
 
    available_slots = serializers.SerializerMethodField()
    is_past         = serializers.SerializerMethodField()
 
    class Meta:
        model  = DonationCamp
        fields = [
            'id',
            'title',
            'description',
            'hospital_name',
            'date',
            'start_time',
            'end_time',
            'location',
            'total_slots',
            'filled_slots',
            'is_urgent',
            'available_slots',
            'is_past',
        ]
 
    def get_available_slots(self, obj):
        return max(0, (obj.total_slots or 0) - (obj.filled_slots or 0))
 
    def get_is_past(self, obj):
        from django.utils import timezone
        return obj.date < timezone.localdate()