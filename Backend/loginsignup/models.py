from django.db import models

class Patient(models.Model):
    fullname = models.CharField(max_length=100)
    emailaddress = models.EmailField(unique=True)
    phonenumber = models.CharField(max_length=15)
    address = models.CharField(max_length=255)
    password = models.CharField(max_length=128)
    confirm_password = models.CharField(max_length=128)
    document_picture = models.ImageField(upload_to='patient_documents/')

    def __str__(self):
        return self.fullname
