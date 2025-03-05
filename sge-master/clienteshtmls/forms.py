from django import forms
from . import models


class ClientehtmlForm(forms.ModelForm):

    class Meta:
        model = models.Clienteshtml
        fields = ['TOKEN_UUID', 'CLIENT_HTML']
        widgets = {
            'TOKEN_UUID': forms.TextInput(attrs={'class': 'form-control'}),
            'CLIENT_HTML': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'TOKEN_UUID': 'TOKEN_UUID',
            'CLIENT_HTML': 'CLIENT_HTML',
        }
