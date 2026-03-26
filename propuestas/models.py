from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum

from empresas.models import CartaFianza, Empresa, Fideicomiso


dni_validator = RegexValidator(
    regex=r"^[0-9A-Za-z\-]+$",
    message="Solo se permiten letras, números y guiones.",
)
ruc_validator = RegexValidator(
    regex=r"^\d{11}$",
    message="Debes ingresar un RUC válido de 11 dígitos.",
)


def propuesta_document_upload_to(instance, filename):
    propuesta_id = instance.propuesta_id or "sin-propuesta"
    return f"propuestas/{propuesta_id}/{filename}"


class PropuestaQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(is_deleted=False)

    def eliminados(self):
        return self.filter(is_deleted=True)


class Propuesta(models.Model):
    class TipoPropuesta(models.TextChoices):
        CARTA_FIANZA = "CF", "Carta Fianza"
        FIDEICOMISO = "FD", "Fideicomiso"

    class Moneda(models.TextChoices):
        SOLES = "S/", "Soles"
        DOLARES = "$", "Dólares"
        EUROS = "€", "Euros"

    class ComisionTipo(models.TextChoices):
        IGV = "IGV", "IGV"
        SIN_IGV = "SIN_IGV", "Sin IGV"
        CON_RETENCION = "CON_RET", "Con retención"

    class ComisionCuenta(models.TextChoices):
        BBVA = "BBVA", "BBVA"
        INTERBANK = "INTERBANK", "Interbank"
        BCP = "BCP", "BCP"
        OTROS = "OTROS", "Otros"

    class EstadoPago(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CON_ADELANTOS = "con_adelantos", "Con adelantos"
        CANCELADA = "cancelada", "Cancelada"

    objects = PropuestaQuerySet.as_manager()

    tipo_propuesta = models.CharField(
        max_length=2,
        choices=TipoPropuesta.choices,
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="propuestas",
    )

    # Snapshot empresa / consorcio
    # Snapshot empresa / consorcio
    empresa_nombre_snapshot = models.CharField(max_length=200, blank=True)
    es_consorcio_snapshot = models.BooleanField(default=False)
    representante_legal_snapshot = models.CharField(max_length=200, blank=True)
    dni_representante_snapshot = models.CharField(
        max_length=20,
        blank=True,
        validators=[dni_validator],
    )
    consorcio_integrantes_snapshot = models.TextField(blank=True, default="")

    # Datos propios de la propuesta
    facturador_texto = models.CharField(
        max_length=200,
        validators=[ruc_validator],
    )
    entidad = models.CharField(max_length=200, blank=True, default="")
    monto_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    moneda = models.CharField(
        max_length=3,
        choices=Moneda.choices,
        default=Moneda.SOLES,
    )

    # Comisión
    comision_monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    comision_fecha = models.DateField()
    comision_moneda = models.CharField(
        max_length=3,
        choices=Moneda.choices,
        default=Moneda.SOLES,
    )
    comision_tipo = models.CharField(
        max_length=10,
        choices=ComisionTipo.choices,
        default=ComisionTipo.IGV,
    )
    comision_cuenta = models.CharField(
        max_length=12,
        choices=ComisionCuenta.choices,
        default=ComisionCuenta.BBVA,
    )
    comision_cuenta_otro = models.CharField(max_length=100, blank=True)

    observaciones_generales = models.TextField(blank=True)
    fecha_propuesta = models.DateField(auto_now_add=True)

    # Totales calculados
    estado_pago_actual = models.CharField(
        max_length=20,
        choices=EstadoPago.choices,
        default=EstadoPago.PENDIENTE,
    )
    total_adelantado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_cancelado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_pagado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    saldo_pendiente = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tipos_relacionados = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Tipos seleccionados manualmente para la propuesta."
    )

    TIPOS_CF = [
        ("AD", "Adelanto Directo"),
        ("AM", "Adelanto de Materiales"),
        ("FC", "Fiel Cumplimiento"),
    ]

    TIPOS_FD = [
        ("AD", "Adelanto Directo"),
        ("AM", "Adelanto de Materiales"),
    ]

    def get_tipos_relacionados_list(self):
        return [x for x in (self.tipos_relacionados or "").split(",") if x]

    def get_tipos_relacionados_display_list(self):
        choices = dict(self.TIPOS_CF if self.tipo_propuesta == self.TipoPropuesta.CARTA_FIANZA else self.TIPOS_FD)
        return [choices[c] for c in self.get_tipos_relacionados_list() if c in choices]

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_actualizadas",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="propuestas_borradas",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["empresa"]),
            models.Index(fields=["tipo_propuesta"]),
            models.Index(fields=["estado_pago_actual"]),
            models.Index(fields=["fecha_propuesta"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self):
        return f"Propuesta #{self.pk or 'nueva'} - {self.get_tipo_propuesta_display()}"

    @property
    def codigo(self):
        return f"PROP-{self.pk}" if self.pk else "PROP-NUEVA"

    def sync_snapshot_empresa(self):
        if not self.empresa_id:
            return

        self.empresa_nombre_snapshot = self.empresa.nombre_consorcio or self.empresa.nombre or ""
        self.es_consorcio_snapshot = bool(self.empresa.es_consorcio)
        self.representante_legal_snapshot = self.empresa.representante_legal or ""
        self.dni_representante_snapshot = self.empresa.dni_representante or ""
        self.consorcio_integrantes_snapshot = self.empresa.empresas_consorciadas or ""

    def recalculate_totals(self, save=True):
        agg = self.movimientos.aggregate(
            adelantos=Sum(
                "monto",
                filter=models.Q(tipo_movimiento=PropuestaMovimientoPago.TipoMovimiento.ADELANTO),
            ),
            cancelado=Sum(
                "monto",
                filter=models.Q(tipo_movimiento=PropuestaMovimientoPago.TipoMovimiento.CANCELACION),
            ),
            total=Sum("monto"),
        )

        self.total_adelantado = agg["adelantos"] or Decimal("0.00")
        self.total_cancelado = agg["cancelado"] or Decimal("0.00")
        self.total_pagado = agg["total"] or Decimal("0.00")

        self.saldo_pendiente = (self.monto_total or Decimal("0.00")) - self.total_pagado
        if self.saldo_pendiente < Decimal("0.00"):
            self.saldo_pendiente = Decimal("0.00")

        if self.total_pagado <= Decimal("0.00"):
            self.estado_pago_actual = self.EstadoPago.PENDIENTE
        elif (self.monto_total or Decimal("0.00")) > Decimal("0.00") and self.total_pagado >= self.monto_total:
            self.estado_pago_actual = self.EstadoPago.CANCELADA
        else:
            self.estado_pago_actual = self.EstadoPago.CON_ADELANTOS

        if save and self.pk:
            self.save(
                update_fields=[
                    "total_adelantado",
                    "total_cancelado",
                    "total_pagado",
                    "saldo_pendiente",
                    "estado_pago_actual",
                    "updated_at",
                ]
            )

    def clean(self):
        errors = {}

        if self.comision_cuenta == self.ComisionCuenta.OTROS and not self.comision_cuenta_otro.strip():
            errors["comision_cuenta_otro"] = "Debes especificar la cuenta cuando eliges 'Otros'."

        facturar = (self.facturador_texto or "").strip()
        if not facturar or not facturar.isdigit() or len(facturar) != 11:
            errors["facturador_texto"] = "Debes ingresar un RUC válido de 11 dígitos."

        if not (self.entidad or "").strip():
            errors["entidad"] = "Debes indicar la entidad."

        if self.es_consorcio_snapshot:
            if not self.representante_legal_snapshot.strip():
                errors["representante_legal_snapshot"] = "El representante legal es obligatorio para consorcio."
            if not self.dni_representante_snapshot.strip():
                errors["dni_representante_snapshot"] = "El DNI/C.E. es obligatorio para consorcio."

        tipos = self.get_tipos_relacionados_list()
        permitidos = {
            codigo
            for codigo, _ in (
                self.TIPOS_CF
                if self.tipo_propuesta == self.TipoPropuesta.CARTA_FIANZA
                else self.TIPOS_FD
            )
        }

        if not tipos:
            errors["tipos_relacionados"] = "Debes seleccionar al menos un tipo."
        elif any(tipo not in permitidos for tipo in tipos):
            errors["tipos_relacionados"] = "Hay tipos relacionados inválidos para esta propuesta."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.empresa_id and not self.empresa_nombre_snapshot:
            self.sync_snapshot_empresa()

        self.facturador_texto = (self.facturador_texto or "").strip()
        self.entidad = (self.entidad or "").strip()

        permitidos = {
            codigo
            for codigo, _ in (
                self.TIPOS_CF
                if self.tipo_propuesta == self.TipoPropuesta.CARTA_FIANZA
                else self.TIPOS_FD
            )
        }

        tipos_limpios = []
        for tipo in (self.tipos_relacionados or "").split(","):
            tipo = tipo.strip()
            if tipo and tipo in permitidos and tipo not in tipos_limpios:
                tipos_limpios.append(tipo)

        self.tipos_relacionados = ",".join(tipos_limpios)

        if not self.saldo_pendiente and self.monto_total:
            self.saldo_pendiente = self.monto_total - (self.total_pagado or Decimal("0.00"))

        super().save(*args, **kwargs)


class PropuestaRelacionCartaFianza(models.Model):
    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.CASCADE,
        related_name="relaciones_cartas",
    )
    carta_fianza = models.ForeignKey(
        CartaFianza,
        on_delete=models.PROTECT,
        related_name="propuestas_relacionadas",
    )
    orden = models.PositiveIntegerField(default=1)

    snapshot_numero_carta = models.CharField(max_length=50, blank=True)
    snapshot_aseguradora = models.CharField(max_length=100, blank=True)
    snapshot_tipo_carta = models.CharField(max_length=100, blank=True)
    snapshot_monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    snapshot_entidad_beneficiaria = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["propuesta", "carta_fianza"],
                name="uq_propuesta_carta_fianza",
            ),
            models.UniqueConstraint(
                fields=["propuesta", "orden"],
                name="uq_propuesta_carta_orden",
            ),
        ]

    def __str__(self):
        return f"{self.propuesta.codigo} - Carta {self.orden}"

    def sync_snapshot(self):
        carta = self.carta_fianza
        self.snapshot_numero_carta = carta.numero_fianza or ""
        self.snapshot_aseguradora = (
            carta.aseguradora_otro if getattr(carta, "aseguradora", "") == "OTROS" and getattr(carta, "aseguradora_otro", "") else carta.aseguradora or ""
        )
        self.snapshot_tipo_carta = carta.tipo_carta or ""
        self.snapshot_monto = carta.monto or Decimal("0.00")
        self.snapshot_entidad_beneficiaria = carta.entidad or ""

    def clean(self):
        errors = {}
        if self.propuesta.tipo_propuesta != Propuesta.TipoPropuesta.CARTA_FIANZA:
            errors["propuesta"] = "Solo una propuesta de Carta Fianza puede tener cartas relacionadas."

        if self.propuesta_id and self.carta_fianza_id:
            existe = PropuestaRelacionCartaFianza.objects.filter(
                propuesta=self.propuesta,
                carta_fianza=self.carta_fianza,
            )
            if self.pk:
                existe = existe.exclude(pk=self.pk)
            if existe.exists():
                errors["carta_fianza"] = "Esta carta fianza ya fue agregada a la propuesta."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.carta_fianza_id and not self.snapshot_numero_carta:
            self.sync_snapshot()

        if not self.orden:
            ultimo = (
                PropuestaRelacionCartaFianza.objects.filter(propuesta=self.propuesta)
                .aggregate(max_orden=models.Max("orden"))
                .get("max_orden")
            )
            self.orden = (ultimo or 0) + 1

        super().save(*args, **kwargs)


class PropuestaRelacionFideicomiso(models.Model):
    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.CASCADE,
        related_name="relaciones_fideicomisos",
    )
    fideicomiso = models.ForeignKey(
        Fideicomiso,
        on_delete=models.PROTECT,
        related_name="propuestas_relacionadas",
    )
    orden = models.PositiveIntegerField(default=1)

    snapshot_fiduciaria = models.CharField(max_length=200, blank=True)
    snapshot_ejecutora = models.CharField(max_length=200, blank=True)
    snapshot_representante = models.CharField(max_length=200, blank=True)
    snapshot_residente = models.CharField(max_length=200, blank=True)
    snapshot_estado = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["propuesta", "fideicomiso"],
                name="uq_propuesta_fideicomiso",
            ),
            models.UniqueConstraint(
                fields=["propuesta", "orden"],
                name="uq_propuesta_fideicomiso_orden",
            ),
        ]

    def __str__(self):
        return f"{self.propuesta.codigo} - Fideicomiso {self.orden}"

    def sync_snapshot(self):
        fidei = self.fideicomiso
        self.snapshot_fiduciaria = getattr(fidei, "fiduciaria", "") or ""
        self.snapshot_ejecutora = getattr(fidei, "ejecutora", "") or ""
        self.snapshot_representante = getattr(fidei, "representante", "") or ""
        self.snapshot_residente = getattr(fidei, "residente", "") or ""
        self.snapshot_estado = getattr(fidei, "estado", "") or ""

    def clean(self):
        errors = {}
        if self.propuesta.tipo_propuesta != Propuesta.TipoPropuesta.FIDEICOMISO:
            errors["propuesta"] = "Solo una propuesta de Fideicomiso puede tener fideicomisos relacionados."

        if self.propuesta_id and self.fideicomiso_id:
            existe = PropuestaRelacionFideicomiso.objects.filter(
                propuesta=self.propuesta,
                fideicomiso=self.fideicomiso,
            )
            if self.pk:
                existe = existe.exclude(pk=self.pk)
            if existe.exists():
                errors["fideicomiso"] = "Este fideicomiso ya fue agregado a la propuesta."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.fideicomiso_id and not self.snapshot_fiduciaria:
            self.sync_snapshot()

        if not self.orden:
            ultimo = (
                PropuestaRelacionFideicomiso.objects.filter(propuesta=self.propuesta)
                .aggregate(max_orden=models.Max("orden"))
                .get("max_orden")
            )
            self.orden = (ultimo or 0) + 1

        super().save(*args, **kwargs)


class PropuestaMovimientoPago(models.Model):
    class TipoMovimiento(models.TextChoices):
        ADELANTO = "adelanto", "Adelanto"
        CANCELACION = "cancelacion", "Cancelación"

    class MedioPago(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        CHEQUE = "cheque", "Cheque"
        DEPOSITO = "deposito", "Depósito"

    class TipoComprobante(models.TextChoices):
        RH = "RH", "RH"
        FACTURA = "FACTURA", "Factura"
        SIN_COMPROBANTE = "SIN", "Sin comprobante"

    class FacturaModalidad(models.TextChoices):
        CONTADO = "contado", "Contado"
        CREDITO = "credito", "Crédito"

    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.CASCADE,
        related_name="movimientos",
    )
    tipo_movimiento = models.CharField(
        max_length=20,
        choices=TipoMovimiento.choices,
    )
    orden = models.PositiveIntegerField(default=1)
    fecha = models.DateField()
    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    medio_pago = models.CharField(
        max_length=10,
        choices=MedioPago.choices,
    )
    observaciones = models.TextField(blank=True)

    tipo_comprobante = models.CharField(
        max_length=10,
        choices=TipoComprobante.choices,
        default=TipoComprobante.SIN_COMPROBANTE,
    )

    # RH
    rh_tiene_retencion = models.BooleanField(default=False)
    rh_retencion_monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Factura
    factura_modalidad = models.CharField(
        max_length=10,
        choices=FacturaModalidad.choices,
        blank=True,
    )
    factura_fecha_vencimiento = models.DateField(null=True, blank=True)
    factura_credito_cancelado = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha", "orden", "id"]
        indexes = [
            models.Index(fields=["propuesta"]),
            models.Index(fields=["tipo_movimiento"]),
            models.Index(fields=["fecha"]),
            models.Index(fields=["tipo_comprobante"]),
        ]

    def __str__(self):
        return f"{self.propuesta.codigo if self.propuesta_id else 'PROP-SIN-GUARDAR'} - {self.get_tipo_movimiento_display()} - {self.monto}"

    def clean(self):
        errors = {}

        # Permitir propuesta asignada en memoria aunque todavía no tenga pk
        if not getattr(self, "propuesta", None):
            raise ValidationError("El movimiento debe pertenecer a una propuesta.")

        # Validaciones contra base de datos solo si la propuesta ya existe
        if self.propuesta_id:
            qs = PropuestaMovimientoPago.objects.filter(propuesta_id=self.propuesta_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            

        # Validaciones por comprobante
        if self.tipo_comprobante == self.TipoComprobante.RH:
            if self.factura_modalidad:
                errors["factura_modalidad"] = "No corresponde cuando el comprobante es RH."
            if self.factura_fecha_vencimiento:
                errors["factura_fecha_vencimiento"] = "No corresponde cuando el comprobante es RH."
            if self.factura_credito_cancelado is not None:
                errors["factura_credito_cancelado"] = "No corresponde cuando el comprobante es RH."

            if self.rh_tiene_retencion:
                if not self.rh_retencion_monto or self.rh_retencion_monto <= 0:
                    errors["rh_retencion_monto"] = "Debes indicar el monto de retención."
            else:
                self.rh_retencion_monto = None

        elif self.tipo_comprobante == self.TipoComprobante.FACTURA:
            if self.rh_tiene_retencion:
                errors["rh_tiene_retencion"] = "No corresponde cuando el comprobante es Factura."
            if self.rh_retencion_monto:
                errors["rh_retencion_monto"] = "No corresponde cuando el comprobante es Factura."

            if not self.factura_modalidad:
                errors["factura_modalidad"] = "Debes indicar si la factura es contado o crédito."

            if self.factura_modalidad == self.FacturaModalidad.CONTADO:
                if self.factura_fecha_vencimiento:
                    errors["factura_fecha_vencimiento"] = "No corresponde en factura al contado."
                if self.factura_credito_cancelado is not None:
                    errors["factura_credito_cancelado"] = "No corresponde en factura al contado."

            if self.factura_modalidad == self.FacturaModalidad.CREDITO:
                if not self.factura_fecha_vencimiento:
                    errors["factura_fecha_vencimiento"] = "Debes indicar la fecha de vencimiento."
                if self.factura_credito_cancelado is None:
                    errors["factura_credito_cancelado"] = "Debes indicar si el crédito ya fue cancelado."

        elif self.tipo_comprobante == self.TipoComprobante.SIN_COMPROBANTE:
            if self.rh_tiene_retencion:
                errors["rh_tiene_retencion"] = "No corresponde sin comprobante."
            if self.rh_retencion_monto:
                errors["rh_retencion_monto"] = "No corresponde sin comprobante."
            if self.factura_modalidad:
                errors["factura_modalidad"] = "No corresponde sin comprobante."
            if self.factura_fecha_vencimiento:
                errors["factura_fecha_vencimiento"] = "No corresponde sin comprobante."
            if self.factura_credito_cancelado is not None:
                errors["factura_credito_cancelado"] = "No corresponde sin comprobante."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.orden and self.propuesta_id:
            ultimo = (
                PropuestaMovimientoPago.objects.filter(propuesta_id=self.propuesta_id)
                .aggregate(max_orden=models.Max("orden"))
                .get("max_orden")
            )
            self.orden = (ultimo or 0) + 1

        super().save(*args, **kwargs)

        if self.propuesta_id:
            self.propuesta.recalculate_totals(save=True)

    def delete(self, *args, **kwargs):
        propuesta = self.propuesta
        super().delete(*args, **kwargs)
        if getattr(propuesta, "id", None):
            propuesta.recalculate_totals(save=True)

class PropuestaDocumento(models.Model):
    class Categoria(models.TextChoices):
        PROPUESTA_GENERAL = "propuesta_general", "Propuesta general"
        MOVIMIENTO_SOPORTE = "movimiento_soporte", "Soporte de movimiento"
        RH_RETENCION = "rh_retencion", "RH retención"
        FACTURA = "factura", "Factura"
        DETRACCION = "detraccion", "Detracción"

    propuesta = models.ForeignKey(
        Propuesta,
        on_delete=models.CASCADE,
        related_name="documentos",
    )
    movimiento = models.ForeignKey(
        PropuestaMovimientoPago,
        on_delete=models.CASCADE,
        related_name="documentos",
        null=True,
        blank=True,
    )
    categoria = models.CharField(
        max_length=30,
        choices=Categoria.choices,
    )
    archivo = models.FileField(
        upload_to=propuesta_document_upload_to,
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )
    nombre_original = models.CharField(max_length=255, blank=True)
    descripcion = models.CharField(max_length=255, blank=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_propuesta_subidos",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.nombre_original or self.archivo.name.split("/")[-1]

    def clean(self):
        errors = {}

        if self.movimiento_id and self.movimiento.propuesta_id != self.propuesta_id:
            raise ValidationError("El movimiento debe pertenecer a la misma propuesta.")

        if self.categoria == self.Categoria.PROPUESTA_GENERAL and self.movimiento_id:
            errors["categoria"] = "La categoría 'propuesta general' no debe ligarse a un movimiento."

        if self.movimiento_id is None:
            if self.categoria != self.Categoria.PROPUESTA_GENERAL:
                raise ValidationError("Esta categoría requiere un movimiento asociado.")
            if errors:
                raise ValidationError(errors)
            return

        movimiento = self.movimiento

        if self.categoria == self.Categoria.MOVIMIENTO_SOPORTE:
            if movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.SIN_COMPROBANTE:
             raise ValidationError("La categoría 'Sin comprobante' solo puede usarse cuando el movimiento fue registrado sin comprobante.")

        if self.categoria == self.Categoria.RH_RETENCION:
            if (
                movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.RH
                or not movimiento.rh_tiene_retencion
            ):
                raise ValidationError("Solo puedes subir 'RH retención' cuando el movimiento es RH con retención.")

        if self.categoria == self.Categoria.FACTURA:
            if movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.FACTURA:
                raise ValidationError("Solo puedes subir 'Factura' cuando el movimiento tiene comprobante Factura.")

        if self.categoria == self.Categoria.DETRACCION:
            if movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.FACTURA:
                raise ValidationError("Solo puedes subir 'Detracción' cuando el movimiento tiene comprobante Factura.")
            if (
                movimiento.factura_modalidad == PropuestaMovimientoPago.FacturaModalidad.CREDITO
                and movimiento.factura_credito_cancelado is not True
            ):
                raise ValidationError("En factura a crédito, la detracción solo puede subirse cuando el crédito ya fue cancelado.")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.nombre_original and self.archivo:
            self.nombre_original = self.archivo.name.split("/")[-1]
        super().save(*args, **kwargs)