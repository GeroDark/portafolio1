from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .forms import (
    PropuestaMovimientoPagoForm,
    PropuestaRelacionCartaFianzaForm,
    PropuestaRelacionFideicomisoForm,
)
from .models import (
    Propuesta,
    PropuestaMovimientoPago,
    PropuestaRelacionCartaFianza,
    PropuestaRelacionFideicomiso,
)

# Funcionalidad antigua de relación con registros existentes.
# Se conserva para una posible reactivación futura, pero el flujo actual
# de crear/editar propuesta ya no usa estos formsets.
class BasePropuestaRelacionCartaFianzaFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        if self.instance.tipo_propuesta != Propuesta.TipoPropuesta.CARTA_FIANZA:
            return

        activos = 0
        repetidos = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            carta = form.cleaned_data.get("carta_fianza")
            if not carta:
                continue

            activos += 1

            if carta.pk in repetidos:
                form.add_error("carta_fianza", "Esta carta fianza está repetida en la propuesta.")
            repetidos.add(carta.pk)

        if activos == 0:
            raise forms.ValidationError("Debes agregar al menos una carta fianza a la propuesta.")


class BasePropuestaRelacionFideicomisoFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        if self.instance.tipo_propuesta != Propuesta.TipoPropuesta.FIDEICOMISO:
            return

        activos = 0
        repetidos = set()

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            fideicomiso = form.cleaned_data.get("fideicomiso")
            if not fideicomiso:
                continue

            activos += 1

            if fideicomiso.pk in repetidos:
                form.add_error("fideicomiso", "Este fideicomiso está repetido en la propuesta.")
            repetidos.add(fideicomiso.pk)

        if activos == 0:
            raise forms.ValidationError("Debes agregar al menos un fideicomiso a la propuesta.")


class BasePropuestaMovimientoPagoFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["propuesta"] = self.instance
        return kwargs

    def clean(self):
        super().clean()

        if not self.instance:
            return

        base_monto = self.instance.comision_monto or self.instance.monto_total or Decimal("0.00")
        activos = []

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue

            tipo_movimiento = form.cleaned_data.get("tipo_movimiento")
            monto = form.cleaned_data.get("monto")

            # ignorar formularios realmente vacíos
            if not tipo_movimiento and not monto:
                continue

            activos.append((form, form.cleaned_data))

        total = Decimal("0.00")
        cancelaciones = 0
        cancelacion_index = None
        total_antes_cancelacion = Decimal("0.00")

        for idx, (form, cleaned) in enumerate(activos):
            monto = cleaned.get("monto") or Decimal("0.00")
            tipo_movimiento = cleaned.get("tipo_movimiento")

            total += monto

            if total > base_monto:
                form.add_error("monto", "La suma de movimientos no puede superar el monto de comisión de la propuesta.")

            if tipo_movimiento == PropuestaMovimientoPago.TipoMovimiento.CANCELACION:
                cancelaciones += 1
                cancelacion_index = idx
                total_antes_cancelacion = total - monto

        if cancelaciones > 1:
            raise forms.ValidationError("Solo puede existir una cancelación por propuesta.")

        if cancelacion_index is not None:
            cancel_form, cancel_cleaned = activos[cancelacion_index]
            cancel_monto = cancel_cleaned.get("monto") or Decimal("0.00")
            restante = base_monto - total_antes_cancelacion

            if cancel_monto != restante:
                cancel_form.add_error("monto", "La cancelación debe cerrar exactamente el saldo restante.")

            if cancelacion_index != len(activos) - 1:
                raise forms.ValidationError("No puedes agregar movimientos después de una cancelación.")


PropuestaRelacionCartaFianzaFormSet = inlineformset_factory(
    Propuesta,
    PropuestaRelacionCartaFianza,
    form=PropuestaRelacionCartaFianzaForm,
    formset=BasePropuestaRelacionCartaFianzaFormSet,
    extra=0,
    can_delete=True,
)

PropuestaRelacionFideicomisoFormSet = inlineformset_factory(
    Propuesta,
    PropuestaRelacionFideicomiso,
    form=PropuestaRelacionFideicomisoForm,
    formset=BasePropuestaRelacionFideicomisoFormSet,
    extra=0,
    can_delete=True,
)

PropuestaMovimientoPagoFormSet = inlineformset_factory(
    Propuesta,
    PropuestaMovimientoPago,
    form=PropuestaMovimientoPagoForm,
    formset=BasePropuestaMovimientoPagoFormSet,
    extra=0,
    can_delete=True,
)