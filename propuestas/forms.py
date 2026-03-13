from __future__ import annotations
from django.db.models import Sum

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from empresas.models import CartaFianza, Empresa, Fideicomiso

from .models import (
    Propuesta,
    PropuestaDocumento,
    PropuestaMovimientoPago,
    PropuestaRelacionCartaFianza,
    PropuestaRelacionFideicomiso,
)
from .services import snapshot_empresa
from .selectors import cartas_fianza_para_empresa, fideicomisos_para_empresa


INPUT_CLASS = "form-control"
SELECT_CLASS = "form-select"
TEXTAREA_CLASS = "form-control"


class BaseStyledFormMixin:
    """
    Aplica clases CSS básicas a los widgets para que luego el template quede más limpio.
    """

    def apply_bootstrap_classes(self):
        for name, field in self.fields.items():
            widget = field.widget

            if isinstance(widget, forms.Textarea):
                css = TEXTAREA_CLASS
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = SELECT_CLASS
            elif isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.ClearableFileInput):
                css = INPUT_CLASS
            else:
                css = INPUT_CLASS

            current = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{current} {css}".strip()

            if field.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("required", "required")


class BuscarPropuestasForm(BaseStyledFormMixin, forms.Form):
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.all().order_by("nombre", "nombre_consorcio"),
        required=False,
        label="Empresa / Consorcio",
        empty_label="Seleccione una empresa",
    )
    q = forms.CharField(
        required=False,
        label="Buscar",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Buscar por empresa, RUC, gerente, consorcio o representante",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class PropuestaBaseForm(BaseStyledFormMixin, forms.ModelForm):
    es_consorcio_manual = forms.BooleanField(
        required=False,
        label="¿Es consorcio?",
    )
    representante_legal_manual = forms.CharField(
        required=False,
        label="Representante legal",
        max_length=200,
    )
    dni_representante_manual = forms.CharField(
        required=False,
        label="DNI / C.E. del representante",
        max_length=20,
    )

    class Meta:
        model = Propuesta
        fields = [
            "empresa",
            "facturador_texto",
            "monto_total",
            "moneda",
            "comision_monto",
            "comision_fecha",
            "comision_moneda",
            "comision_tipo",
            "comision_cuenta",
            "comision_cuenta_otro",
        ]
        widgets = {
            "comision_fecha": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }
        labels = {
            "empresa": "Empresa / Consorcio",
            "facturador_texto": "Facturador",
            "monto_total": "Monto total de la propuesta",
            "moneda": "Moneda propuesta",
            "comision_monto": "Monto de comisión",
            "comision_fecha": "Fecha de comisión",
            "comision_moneda": "Moneda de comisión",
            "comision_tipo": "Tipo de comisión",
            "comision_cuenta": "Cuenta",
            "comision_cuenta_otro": "Especifique otra cuenta",
        }

    fixed_tipo_propuesta = None

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = Empresa.objects.all().order_by("nombre", "nombre_consorcio")
        self.fields["comision_cuenta_otro"].required = False
        self.fields["representante_legal_manual"].required = False
        self.fields["dni_representante_manual"].required = False
        self.fields["comision_fecha"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["comision_fecha"].widget.format = "%Y-%m-%d"

        self.apply_bootstrap_classes()

        self.fields["empresa"].widget.attrs.update(
            {"data-autocomplete-url": "/propuestas/ajax/empresas/"}
        )

        empresa_actual = None
        if getattr(self.instance, "empresa_id", None):
            empresa_actual = self.instance.empresa
        else:
            empresa_inicial = self.initial.get("empresa")
            if empresa_inicial:
                try:
                    empresa_actual = Empresa.objects.get(pk=empresa_inicial)
                except Empresa.DoesNotExist:
                    empresa_actual = None

        if self.instance and self.instance.pk:
            self.fields["es_consorcio_manual"].initial = self.instance.es_consorcio_snapshot
            self.fields["representante_legal_manual"].initial = self.instance.representante_legal_snapshot
            self.fields["dni_representante_manual"].initial = self.instance.dni_representante_snapshot
            self.fields["empresa"].help_text = "Selecciona la empresa o consorcio de la propuesta."
        elif empresa_actual:
            data_snapshot = snapshot_empresa(empresa_actual)
            self.fields["es_consorcio_manual"].initial = data_snapshot.get("es_consorcio_snapshot", False)
            self.fields["representante_legal_manual"].initial = data_snapshot.get("representante_legal_snapshot", "")
            self.fields["dni_representante_manual"].initial = data_snapshot.get("dni_representante_snapshot", "")
            self.fields["empresa"].help_text = "Selecciona la empresa o consorcio de la propuesta."
        else:
            self.fields["empresa"].help_text = "Selecciona la empresa o consorcio de la propuesta."

    def clean(self):
        cleaned_data = super().clean()

        cuenta = cleaned_data.get("comision_cuenta")
        cuenta_otro = (cleaned_data.get("comision_cuenta_otro") or "").strip()

        es_consorcio = bool(cleaned_data.get("es_consorcio_manual"))
        representante = (cleaned_data.get("representante_legal_manual") or "").strip()
        dni = (cleaned_data.get("dni_representante_manual") or "").strip()

        if cuenta == Propuesta.ComisionCuenta.OTROS and not cuenta_otro:
            self.add_error("comision_cuenta_otro", "Debes especificar la cuenta cuando eliges 'Otros'.")

        if es_consorcio:
            if not representante:
                self.add_error("representante_legal_manual", "Debes indicar el representante legal.")
            if not dni:
                self.add_error("dni_representante_manual", "Debes indicar el DNI / C.E. del representante.")
        else:
            cleaned_data["representante_legal_manual"] = ""
            cleaned_data["dni_representante_manual"] = ""

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.fixed_tipo_propuesta:
            instance.tipo_propuesta = self.fixed_tipo_propuesta

        if instance.empresa_id:
            instance.sync_snapshot_empresa()

        instance.es_consorcio_snapshot = bool(self.cleaned_data.get("es_consorcio_manual"))
        instance.representante_legal_snapshot = (
            (self.cleaned_data.get("representante_legal_manual") or "").strip()
            if instance.es_consorcio_snapshot
            else ""
        )
        instance.dni_representante_snapshot = (
            (self.cleaned_data.get("dni_representante_manual") or "").strip()
            if instance.es_consorcio_snapshot
            else ""
        )

        # ya no se usa en pantalla
        instance.observaciones_generales = ""

        if self.request_user:
            if not instance.pk and not instance.creado_por_id:
                instance.creado_por = self.request_user
            instance.actualizado_por = self.request_user

        if commit:
            instance.save()

        return instance

class PropuestaCFForm(PropuestaBaseForm):
    fixed_tipo_propuesta = Propuesta.TipoPropuesta.CARTA_FIANZA


class PropuestaFDForm(PropuestaBaseForm):
    fixed_tipo_propuesta = Propuesta.TipoPropuesta.FIDEICOMISO


class PropuestaRelacionCartaFianzaForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PropuestaRelacionCartaFianza
        fields = ["carta_fianza"]
        labels = {
            "carta_fianza": "Carta fianza",
        }

    def __init__(self, *args, **kwargs):
        propuesta = kwargs.pop("propuesta", None)
        super().__init__(*args, **kwargs)

        self.propuesta = propuesta or getattr(self.instance, "propuesta", None)

        empresa_id = None
        if self.propuesta and getattr(self.propuesta, "empresa_id", None):
            empresa_id = self.propuesta.empresa_id
        elif getattr(self.instance, "propuesta_id", None):
            empresa_id = self.instance.propuesta.empresa_id

        qs = cartas_fianza_para_empresa(empresa_id)

        self.fields["carta_fianza"].queryset = qs.order_by("-id")
        self.fields["carta_fianza"].widget.attrs.update(
            {
                "data-autocomplete-url": "/propuestas/ajax/cartas-fianza/",
            }
        )

        self.apply_bootstrap_classes()

    def clean(self):
        cleaned_data = super().clean()
        carta = cleaned_data.get("carta_fianza")

        if self.propuesta and self.propuesta.tipo_propuesta != Propuesta.TipoPropuesta.CARTA_FIANZA:
            raise ValidationError("Solo una propuesta de Carta Fianza puede tener cartas relacionadas.")

        if self.propuesta and carta and getattr(self.propuesta, "empresa_id", None):
            ids_validos = set(
                cartas_fianza_para_empresa(self.propuesta.empresa_id).values_list("id", flat=True)
            )
            if carta.id not in ids_validos:
                self.add_error(
                    "carta_fianza",
                    "Solo puedes agregar cartas fianza vinculadas a la empresa seleccionada."
                )

        if self.propuesta and self.propuesta.pk and carta:
            qs = PropuestaRelacionCartaFianza.objects.filter(
                propuesta_id=self.propuesta.pk,
                carta_fianza=carta,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("carta_fianza", "Esta carta fianza ya fue agregada a la propuesta.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.propuesta and not instance.propuesta_id:
            instance.propuesta = self.propuesta

        if not instance.pk:
            instance.orden = 0

        if commit:
            instance.save()

        return instance

class PropuestaRelacionFideicomisoForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PropuestaRelacionFideicomiso
        fields = ["fideicomiso"]
        labels = {
            "fideicomiso": "Fideicomiso",
        }

    def __init__(self, *args, **kwargs):
        propuesta = kwargs.pop("propuesta", None)
        super().__init__(*args, **kwargs)

        self.propuesta = propuesta or getattr(self.instance, "propuesta", None)

        empresa_id = None
        if self.propuesta and getattr(self.propuesta, "empresa_id", None):
            empresa_id = self.propuesta.empresa_id
        elif getattr(self.instance, "propuesta_id", None):
            empresa_id = self.instance.propuesta.empresa_id

        qs = fideicomisos_para_empresa(empresa_id)

        self.fields["fideicomiso"].queryset = qs.order_by("-id")
        self.fields["fideicomiso"].widget.attrs.update(
            {
                "data-autocomplete-url": "/propuestas/ajax/fideicomisos/",
            }
        )

        self.apply_bootstrap_classes()

    def clean(self):
        cleaned_data = super().clean()
        fideicomiso = cleaned_data.get("fideicomiso")

        if self.propuesta and self.propuesta.tipo_propuesta != Propuesta.TipoPropuesta.FIDEICOMISO:
            raise ValidationError("Solo una propuesta de Fideicomiso puede tener fideicomisos relacionados.")

        if self.propuesta and fideicomiso and getattr(self.propuesta, "empresa_id", None):
            ids_validos = set(
                fideicomisos_para_empresa(self.propuesta.empresa_id).values_list("id", flat=True)
            )
            if fideicomiso.id not in ids_validos:
                self.add_error(
                    "fideicomiso",
                    "Solo puedes agregar fideicomisos vinculados a la empresa seleccionada.",
                )

        if self.propuesta and self.propuesta.pk and fideicomiso:
            qs = PropuestaRelacionFideicomiso.objects.filter(
                propuesta_id=self.propuesta.pk,
                fideicomiso=fideicomiso,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("fideicomiso", "Este fideicomiso ya fue agregado a la propuesta.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.propuesta and not instance.propuesta_id:
            instance.propuesta = self.propuesta

        if not instance.pk:
            instance.orden = 0

        if commit:
            instance.save()

        return instance

class PropuestaMovimientoPagoForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PropuestaMovimientoPago
        fields = [
            "tipo_movimiento",
            "fecha",
            "monto",
            "medio_pago",
            "observaciones",
            "tipo_comprobante",
            "rh_tiene_retencion",
            "rh_retencion_monto",
            "factura_modalidad",
            "factura_fecha_vencimiento",
            "factura_credito_cancelado",
        ]
        widgets = {
            "fecha": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "factura_fecha_vencimiento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "tipo_movimiento": "Tipo de movimiento",
            "fecha": "Fecha",
            "monto": "Monto",
            "medio_pago": "Medio de pago",
            "observaciones": "Observaciones",
            "tipo_comprobante": "Comprobante",
            "rh_tiene_retencion": "¿Tiene retención?",
            "rh_retencion_monto": "Monto de retención",
            "factura_modalidad": "Modalidad de factura",
            "factura_fecha_vencimiento": "Fecha de vencimiento",
            "factura_credito_cancelado": "¿Crédito cancelado?",
        }

    def __init__(self, *args, **kwargs):
        self.propuesta = kwargs.pop("propuesta", None)
        super().__init__(*args, **kwargs)

        
        self.fields["rh_retencion_monto"].required = False
        self.fields["factura_modalidad"].required = False
        self.fields["factura_fecha_vencimiento"].required = False
        self.fields["factura_credito_cancelado"].required = False
        self.fields["fecha"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["fecha"].widget.format = "%Y-%m-%d"

        self.fields["factura_fecha_vencimiento"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["factura_fecha_vencimiento"].widget.format = "%Y-%m-%d"

        self.apply_bootstrap_classes()

    def clean(self):
        cleaned_data = super().clean()

        tipo_comprobante = cleaned_data.get("tipo_comprobante")
        rh_tiene_retencion = cleaned_data.get("rh_tiene_retencion")
        rh_retencion_monto = cleaned_data.get("rh_retencion_monto")
        factura_modalidad = cleaned_data.get("factura_modalidad")
        factura_fecha_vencimiento = cleaned_data.get("factura_fecha_vencimiento")
        factura_credito_cancelado = cleaned_data.get("factura_credito_cancelado")

        if self.propuesta is None and getattr(self.instance, "propuesta_id", None):
            self.propuesta = self.instance.propuesta

        if not self.propuesta:
            raise ValidationError("No se pudo determinar la propuesta del movimiento.")

        if tipo_comprobante == PropuestaMovimientoPago.TipoComprobante.RH:
            if factura_modalidad:
                self.add_error("factura_modalidad", "No corresponde cuando el comprobante es RH.")
            if factura_fecha_vencimiento:
                self.add_error("factura_fecha_vencimiento", "No corresponde cuando el comprobante es RH.")
            if factura_credito_cancelado is not None:
                self.add_error("factura_credito_cancelado", "No corresponde cuando el comprobante es RH.")

            if rh_tiene_retencion and not rh_retencion_monto:
                self.add_error("rh_retencion_monto", "Debes indicar el monto de retención.")
            if not rh_tiene_retencion:
                cleaned_data["rh_retencion_monto"] = None

        elif tipo_comprobante == PropuestaMovimientoPago.TipoComprobante.FACTURA:
            if rh_tiene_retencion:
                self.add_error("rh_tiene_retencion", "No corresponde cuando el comprobante es Factura.")
            if rh_retencion_monto:
                self.add_error("rh_retencion_monto", "No corresponde cuando el comprobante es Factura.")

            if not factura_modalidad:
                self.add_error("factura_modalidad", "Debes indicar si la factura es contado o crédito.")

            if factura_modalidad == PropuestaMovimientoPago.FacturaModalidad.CONTADO:
                cleaned_data["factura_fecha_vencimiento"] = None
                cleaned_data["factura_credito_cancelado"] = None

            if factura_modalidad == PropuestaMovimientoPago.FacturaModalidad.CREDITO:
                if not factura_fecha_vencimiento:
                    self.add_error("factura_fecha_vencimiento", "Debes indicar la fecha de vencimiento.")
                if factura_credito_cancelado is None:
                    self.add_error("factura_credito_cancelado", "Debes indicar si el crédito ya fue cancelado.")

        elif tipo_comprobante == PropuestaMovimientoPago.TipoComprobante.SIN_COMPROBANTE:
            cleaned_data["rh_tiene_retencion"] = False
            cleaned_data["rh_retencion_monto"] = None
            cleaned_data["factura_modalidad"] = ""
            cleaned_data["factura_fecha_vencimiento"] = None
            cleaned_data["factura_credito_cancelado"] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.propuesta and not instance.propuesta_id:
            instance.propuesta = self.propuesta

        if not instance.pk:
            instance.orden = 0

        if commit:
            instance.save()

        return instance


class PropuestaDocumentoForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PropuestaDocumento
        fields = ["categoria", "archivo", "descripcion"]
        widgets = {
            "descripcion": forms.TextInput(attrs={"placeholder": "Descripción opcional"}),
        }
        labels = {
            "categoria": "Categoría",
            "archivo": "PDF",
            "descripcion": "Descripción",
        }

    def __init__(self, *args, **kwargs):
        self.propuesta = kwargs.pop("propuesta", None)
        self.movimiento = kwargs.pop("movimiento", None)
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

        # Importante: asignar a la instancia ANTES de is_valid()/full_clean()
        if self.propuesta is not None:
            self.instance.propuesta = self.propuesta

        if self.movimiento is not None:
            self.instance.movimiento = self.movimiento

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo and not archivo.name.lower().endswith(".pdf"):
            raise ValidationError("Solo se permiten archivos PDF.")
        return archivo

    def clean(self):
        cleaned_data = super().clean()
        categoria = cleaned_data.get("categoria")

        if self.movimiento is None:
            if categoria != PropuestaDocumento.Categoria.PROPUESTA_GENERAL:
                raise ValidationError("Esta categoría requiere un movimiento asociado.")
            return cleaned_data

        if categoria == PropuestaDocumento.Categoria.PROPUESTA_GENERAL:
            raise ValidationError("La categoría 'Propuesta general' no debe ligarse a un movimiento.")

        if categoria == PropuestaDocumento.Categoria.RH_RETENCION:
            if (
                self.movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.RH
                or not self.movimiento.rh_tiene_retencion
            ):
                raise ValidationError("Solo puedes subir 'RH retención' cuando el movimiento es RH con retención.")

        if categoria == PropuestaDocumento.Categoria.FACTURA:
            if self.movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.FACTURA:
                raise ValidationError("Solo puedes subir 'Factura' cuando el movimiento tiene comprobante Factura.")

        if categoria == PropuestaDocumento.Categoria.DETRACCION:
            if self.movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.FACTURA:
                raise ValidationError("Solo puedes subir 'Detracción' cuando el movimiento tiene comprobante Factura.")
            if (
                self.movimiento.factura_modalidad == PropuestaMovimientoPago.FacturaModalidad.CREDITO
                and self.movimiento.factura_credito_cancelado is not True
            ):
                raise ValidationError("En factura a crédito, la detracción solo puede subirse cuando el crédito ya fue cancelado.")

        if categoria == PropuestaDocumento.Categoria.MOVIMIENTO_SOPORTE:
            if self.movimiento.tipo_comprobante != PropuestaMovimientoPago.TipoComprobante.SIN_COMPROBANTE:
                raise ValidationError("La categoría 'Sin comprobante' solo puede usarse cuando el movimiento fue registrado sin comprobante.")

        return cleaned_data

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)

        if self.propuesta and not instance.propuesta_id:
            instance.propuesta = self.propuesta

        if self.movimiento and not instance.movimiento_id:
            instance.movimiento = self.movimiento

        if user and not instance.subido_por_id:
            instance.subido_por = user

        if commit:
            instance.save()

        return instance