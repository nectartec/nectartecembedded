from django.contrib import admin
from . import models


class ClienteshtmlAdmin(admin.ModelAdmin):
    list_display = ('TOKEN_UUID', 'CLIENT_HTML',)
    search_fields = ('TOKEN_UUID',)


admin.site.register(models.Clienteshtml, ClienteshtmlAdmin)