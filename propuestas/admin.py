from django.contrib import admin

from .models import (
    Propuesta,
    PropuestaDocumento,
    PropuestaMovimientoPago,
    PropuestaRelacionCartaFianza,
    PropuestaRelacionFideicomiso,
)


class PropuestaRelacionCartaFianzaInline(admin.TabularInline):
    model = PropuestaRelacionCartaFianza
    extra = 0


class PropuestaRelacionFideicomisoInline(admin.TabularInline):
    model = PropuestaRelacionFideicomiso
    extra = 0


class PropuestaMovimientoPagoInline(admin.TabularInline):
    model = PropuestaMovimientoPago
    extra = 0


@admin.register(Propuesta)
class PropuestaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo_propuesta",
        "empresa",
        "facturador_texto",
        "monto_total",
        "total_pagado",
        "saldo_pendiente",
        "estado_pago_actual",
        "is_deleted",
    )
    list_filter = ("tipo_propuesta", "estado_pago_actual", "is_deleted", "moneda")
    search_fields = (
        "id",
        "empresa__nombre",
        "empresa__ruc",
        "empresa__nombre_consorcio",
        "facturador_texto",
        "empresa_nombre_snapshot",
    )
    inlines = [
        PropuestaRelacionCartaFianzaInline,
        PropuestaRelacionFideicomisoInline,
        PropuestaMovimientoPagoInline,
    ]


@admin.register(PropuestaDocumento)
class PropuestaDocumentoAdmin(admin.ModelAdmin):
    list_display = ("id", "propuesta", "movimiento", "categoria", "uploaded_at")
    list_filter = ("categoria",)
    search_fields = ("propuesta__id", "nombre_original", "descripcion")