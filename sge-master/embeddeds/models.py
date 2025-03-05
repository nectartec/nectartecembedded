from django.db import models


class Embedded(models.Model):
    CLIENT_ID     = models.CharField(max_length=200, null=True, blank=True)
    CLIENT_SECRET = models.CharField(max_length=200, null=True, blank=True)
    TENANT_ID     = models.CharField(max_length=200, null=True, blank=True)
    WORKSPACE_ID  = models.CharField(max_length=200, null=True, blank=True)
    REPORT_ID     = models.CharField(max_length=200, null=True, blank=True)
    DATASET_ID    = models.CharField(max_length=200, null=True, blank=True)
    class Meta:
        ordering = ['CLIENT_ID']

    def __str__(self):
        return self.CLIENT_ID
