from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# TBD add host names
# ValidHostnameRegex = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$";


class PetData(models.Model):
    class PrimaryIdentifier(models.TextChoices):
        MAC = 'MAC', "MAC"
        HOST = 'HOST', "HOST"
        IP = 'IP', "IP"

    class DeviceType(models.TextChoices):
        PC = 'PC', "PC"
        LAPTOP = 'LAPTOP', "Laptop"
        PHONE = 'PHONE', "Phone"
        IOT = 'IOT', "IoT"
        SERVER = 'SERVER', "Server"
        ROUTER = 'ROUTER', "Router"
        MEDIA = 'MEDIA', "Media"
        GAMES = 'GAMES', "Games"
        OTHER = 'OTHER', "Other"

    name = models.CharField(max_length=64)
    description = models.CharField(max_length=1024)
    creation_date_date = models.DateTimeField("date created", default=timezone.now)
    identifier_type = models.CharField(
        max_length=4,
        choices=PrimaryIdentifier.choices,
        default=PrimaryIdentifier.MAC
    )
    device_type = models.CharField(
        max_length=8,
        choices=DeviceType.choices,
        default=DeviceType.OTHER
    )
    identifier_value = models.CharField(
        max_length=64,
        unique=True
    )

    def __str__(self):
        """Returns a string representation of a message."""
        return f"'{self.name}'"
