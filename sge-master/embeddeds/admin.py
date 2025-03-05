from django.contrib import admin
from . import models


class EmbeddedAdmin(admin.ModelAdmin):
    list_display = ('CLIENT_ID', 'CLIENT_SECRET',)
    search_fields = ('CLIENT_ID',)


admin.site.register(models.Embedded, EmbeddedAdmin)
