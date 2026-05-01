from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hospital", "0008_delete_hospitalauditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospital",
            name="plain_password",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]

