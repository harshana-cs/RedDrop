from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blood_stock", "0004_bloodstockhistory_expiry_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bloodstock",
            name="expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]

