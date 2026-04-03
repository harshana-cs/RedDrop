from rest_framework import serializers
from .models import DonationCamp          # adjust import path to wherever your model lives
 
 
class DonationCampSerializer(serializers.ModelSerializer):
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
            'is_urgent',
            'is_past',
                'contact_number',
                'map_link',
        ]
 
    def get_is_past(self, obj):
        from django.utils import timezone
        return obj.date < timezone.localdate()