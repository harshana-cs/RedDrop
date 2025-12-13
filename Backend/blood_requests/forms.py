from django import forms
from .models import BloodRequest

class BloodRequestForm(forms.ModelForm):
    class Meta:
        model = BloodRequest
        fields = [
            'blood_type', 'units_required', 'urgency', 'district', 'hospital',
            'required_date', 'reason', 'contact_name', 'contact_phone',
            'hospital_doc', 'doctor_note'
        ]
        widgets = {
            'required_date': forms.DateInput(attrs={'type': 'date'}),
        }
