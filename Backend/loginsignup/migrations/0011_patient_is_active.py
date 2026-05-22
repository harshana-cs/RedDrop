from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("loginsignup", "0010_rename_created_on_googlesignup_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]

