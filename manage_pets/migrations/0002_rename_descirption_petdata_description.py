# Generated by Django 5.1 on 2024-11-16 05:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("manage_pets", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="petdata",
            old_name="descirption",
            new_name="description",
        ),
    ]