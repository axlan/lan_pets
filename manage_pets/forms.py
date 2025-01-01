from django import forms

from manage_pets.models import PetData


class LogMessageForm(forms.ModelForm):
    class Meta:
        model = PetData
        fields = ("name", "identifier_type", "mac_address")

    def fields_required(self, fields):
        """Used for conditionally marking fields as required."""
        for field in fields:
            if not self.cleaned_data.get(field, ''):
                msg = forms.ValidationError("This field is required.")
                self.add_error(field, msg)

    def clean(self):
        identifier_type = self.cleaned_data.get('identifier_type')

        if identifier_type is None:
            return self.cleaned_data

        required_field = PetData.IDENTIFIER_MAP[identifier_type]
        if not self.cleaned_data.get(required_field, ''):
            msg = forms.ValidationError("This field is required.")
            self.add_error(required_field, msg)

        # TODO normalize MAC address

        return self.cleaned_data
