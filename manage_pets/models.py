from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# TBD add host names
# ValidHostnameRegex = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$";


class PetData(models.Model):
    class PrimaryIdentifier(models.TextChoices):
        MAC = 'MAC', "MAC"
        HOST = 'HOST', "HOST"
        MDNS = 'MDNS', "mDNS"

    IDENTIFIER_MAP = {
        PrimaryIdentifier.MAC: "mac_address",
        PrimaryIdentifier.HOST: "TBD",
        PrimaryIdentifier.MDNS: "TBD",
    }

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
    mac_address = models.CharField(
        max_length=17,
        unique=True,
        validators=[
            RegexValidator(
                regex='^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$',
                message='Enter a valid MAC address.',
                code='invalid_mac_address'
            ),
        ],
        help_text="Only required if identifier_type is 'MAC'.",
        blank=True
    )

    def __str__(self):
        """Returns a string representation of a message."""
        return f"'{self.name}'"
