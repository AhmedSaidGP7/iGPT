from django import forms
from .models import OpenAISettings

class OpenAISettingsForm(forms.ModelForm):
    model_name = forms.ChoiceField(
        choices=OpenAISettings.MODEL_CHOICES,
        label="Model",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    agent_name = forms.CharField(
        required=True,
        label="Agent Name",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    system_context = forms.CharField(
        required=True,
        label="System Context",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5})
    )

    temperature = forms.FloatField(
        required=True,
        label="Temperature",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '2'})
    )

    top_p = forms.FloatField(
        required=True,
        label="Top P",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '1'})
    )

    frequency_penalty = forms.FloatField(
        required=True,
        label="Frequency Penalty",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '2'})
    )

    presence_penalty = forms.FloatField(
        required=True,
        label="Presence Penalty",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '2'})
    )

    class Meta:
        model = OpenAISettings
        fields = [
            'model_name',
            'agent_name',
            'system_context',
            'temperature',
            'top_p',
            'frequency_penalty',
            'presence_penalty',
        ]
