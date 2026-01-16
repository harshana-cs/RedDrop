from django.db import models
class DonationCamp(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    hospital_name = models.CharField(max_length=200)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200)
    total_slots = models.IntegerField(default=0)
    filled_slots = models.IntegerField(default=0)
    is_urgent = models.BooleanField(default=False)

    def __str__(self):
        return self.title

# Create your models here.
