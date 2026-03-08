from django.contrib import admin
from .models import Empresa, CartaFianza, AvisoVencimiento
# Register your models here.

admin.site.register(Empresa)
admin.site.register(CartaFianza)
@admin.register(AvisoVencimiento)
class AvisoVencimientoAdmin(admin.ModelAdmin):
    list_display = ("carta", "days_before", "sent_at", "subject")
    list_filter = ("days_before", "sent_at")
    search_fields = ("carta__numero_fianza", "carta__empresa__nombre", "recipients")