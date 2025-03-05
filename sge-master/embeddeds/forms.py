from django import forms
from . import models


class EmbeddedForm(forms.ModelForm):

    class Meta:
        model = models.Embedded
        fields = ['CLIENT_ID', 'CLIENT_SECRET','TENANT_ID','WORKSPACE_ID','REPORT_ID','DATASET_ID']
        widgets = {
            'CLIENT_ID': forms.TextInput(attrs={'class': 'form-control'}),
            'CLIENT_SECRET': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'TENANT_ID': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'WORKSPACE_ID': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'REPORT_ID': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'DATASET_ID': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'CLIENT_ID': 'CLIENT_ID',
            'CLIENT_SECRET': 'CLIENT_SECRET',
            'TENANT_ID': 'TENANT_ID',
            'WORKSPACE_ID': 'WORKSPACE_ID',
            'REPORT_ID': 'REPORT_ID',
            'DATASET_ID': 'DATASET_ID',
        }
