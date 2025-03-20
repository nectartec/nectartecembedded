from django.db import models


class Clienteshtml(models.Model):
    TOKEN_UUID = models.CharField(max_length=200, null=True, blank=True)
    REPORT_ID = models.CharField(max_length=200, null=True, blank=True)
    WORKSPACE_ID = models.CharField(max_length=200, null=True, blank=True)
    EMBED_URL = models.CharField(max_length=200, null=True, blank=True)
    EMBED_TOKEN = models.CharField(max_length=200, null=True, blank=True)
    EXPIRES_AT = models.DateTimeField(null=True, blank=True)  # 🔥 Adiciona o campo de validade do token
    CLIENT_HTML = models.CharField(max_length=1000, null=True, blank=True)
    class Meta:
        ordering = ['TOKEN_UUID']

    def __str__(self):
        return self.TOKEN_UUID
 

 