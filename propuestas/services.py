from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    Propuesta,
    PropuestaMovimientoPago,
    PropuestaRelacionCartaFianza,
    PropuestaRelacionFideicomiso,
)


def snapshot_empresa(empresa) -> dict:
    return {
        "empresa_nombre_snapshot": empresa.nombre_consorcio or empresa.nombre or "",
        "es_consorcio_snapshot": bool(getattr(empresa, "es_consorcio", False)),
        "representante_legal_snapshot": getattr(empresa, "representante_legal", "") or "",
        "dni_representante_snapshot": getattr(empresa, "dni_representante", "") or "",
    }


def snapshot_carta_fianza(carta) -> dict:
    aseguradora = getattr(carta, "aseguradora", "") or ""
    if aseguradora == "OTROS" and getattr(carta, "aseguradora_otro", ""):
        aseguradora = carta.aseguradora_otro

    return {
        "snapshot_numero_carta": getattr(carta, "numero_fianza", "") or "",
        "snapshot_aseguradora": aseguradora,
        "snapshot_tipo_carta": getattr(carta, "tipo_carta", "") or "",
        "snapshot_monto": getattr(carta, "monto", Decimal("0.00")) or Decimal("0.00"),
        "snapshot_entidad_beneficiaria": getattr(carta, "entidad", "") or "",
    }


def snapshot_fideicomiso(fideicomiso) -> dict:
    return {
        "snapshot_fiduciaria": getattr(fideicomiso, "fiduciaria", "") or "",
        "snapshot_ejecutora": getattr(fideicomiso, "ejecutora", "") or "",
        "snapshot_representante": getattr(fideicomiso, "representante", "") or "",
        "snapshot_residente": getattr(fideicomiso, "residente", "") or "",
        "snapshot_estado": getattr(fideicomiso, "estado", "") or "",
    }


@transaction.atomic
def sync_propuesta_snapshot_empresa(propuesta: Propuesta, save: bool = True) -> Propuesta:
    data = snapshot_empresa(propuesta.empresa)
    for field, value in data.items():
        setattr(propuesta, field, value)

    if save:
        propuesta.save()

    return propuesta


@transaction.atomic
def recalculate_propuesta_totals(propuesta: Propuesta, save: bool = True) -> Propuesta:
    propuesta.recalculate_totals(save=save)
    return propuesta


@transaction.atomic
def reorder_relaciones_cartas(propuesta: Propuesta) -> None:
    relaciones = propuesta.relaciones_cartas.order_by("orden", "id")
    for index, relacion in enumerate(relaciones, start=1):
        if relacion.orden != index:
            PropuestaRelacionCartaFianza.objects.filter(pk=relacion.pk).update(orden=index)


@transaction.atomic
def reorder_relaciones_fideicomisos(propuesta: Propuesta) -> None:
    relaciones = propuesta.relaciones_fideicomisos.order_by("orden", "id")
    for index, relacion in enumerate(relaciones, start=1):
        if relacion.orden != index:
            PropuestaRelacionFideicomiso.objects.filter(pk=relacion.pk).update(orden=index)


@transaction.atomic
def reorder_movimientos(propuesta: Propuesta) -> None:
    movimientos = propuesta.movimientos.order_by("fecha", "orden", "id")
    for index, movimiento in enumerate(movimientos, start=1):
        if movimiento.orden != index:
            PropuestaMovimientoPago.objects.filter(pk=movimiento.pk).update(orden=index)


@transaction.atomic
def soft_delete_propuesta(propuesta: Propuesta, user=None) -> Propuesta:
    propuesta.is_deleted = True
    propuesta.deleted_at = timezone.now()
    propuesta.deleted_by = user
    propuesta.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
    return propuesta


def validate_propuesta_payments(propuesta: Propuesta) -> None:
    total_pagado = propuesta.total_pagado or Decimal("0.00")
    if total_pagado > propuesta.monto_total:
        raise ValueError("El total pagado no puede superar el monto total de la propuesta.")


def siguiente_orden_relacion_cf(propuesta: Propuesta) -> int:
    max_orden = propuesta.relaciones_cartas.aggregate(max_orden=Max("orden")).get("max_orden") or 0
    return max_orden + 1


def siguiente_orden_relacion_fd(propuesta: Propuesta) -> int:
    max_orden = propuesta.relaciones_fideicomisos.aggregate(max_orden=Max("orden")).get("max_orden") or 0
    return max_orden + 1


def siguiente_orden_movimiento(propuesta: Propuesta) -> int:
    max_orden = propuesta.movimientos.aggregate(max_orden=Max("orden")).get("max_orden") or 0
    return max_orden + 1