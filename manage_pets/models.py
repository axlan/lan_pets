from django.db import models
from django.core.validators import RegexValidator
from datetime import datetime

# TBD add host names
# ValidHostnameRegex = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$";

class PetData(models.Model):
    class PrimaryIdentifier(models.TextChoices):
        IP = 'IP', "IP"
        MAC = 'MAC', "MAC"
        DNS = 'DNS', "DNS"
        MDNS = 'MDNS', "mDNS"

    IDENTIFIER_MAP = {
        PrimaryIdentifier.IP: "ip_address",
        PrimaryIdentifier.MAC: "mac_address",
        PrimaryIdentifier.DNS: "TBD",
        PrimaryIdentifier.MDNS: "TBD",
    }

    name = models.CharField(max_length=64)
    descirption = models.CharField(max_length=1024)
    creation_date_date = models.DateTimeField("date created", default=datetime.now)
    identifier_type = models.CharField(
        max_length=4,
        choices=PrimaryIdentifier.choices,
        default=PrimaryIdentifier.IP
    )
    ip_address = models.GenericIPAddressField(help_text="Only required if identifier_type is 'IP'.",
                                              blank=True, null=True)
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
