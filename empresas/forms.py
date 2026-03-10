from django import forms
from django.forms import modelformset_factory, inlineformset_factory
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import CartaFianza, Empresa, Fideicomiso, ArchivoAdjunto, Desembolso, PagoEmpresa, AdelantoPago, DocumentoPago, CorreoFideicomiso, DocumentoFid, AdelantoFid, LiquidacionFianza
import re
import json
from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import EmailValidator

def romano_a_entero(txt: str) -> int:
    mapa = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
    total = prev = 0
    for ch in reversed(txt.upper()):
        if ch not in mapa:
            raise ValueError
        cur = mapa[ch]
        total += -cur if cur < prev else cur
        prev = cur
    return total

def suma_porcentajes(txt: str) -> bool:
    """Devuelve True si los % entre paréntesis suman 100."""
    import re, math
    p = re.findall(r'\((\d+(?:\.\d+)?)%\)', txt)
    return p and math.isclose(sum(map(float, p)), 100.0, abs_tol=0.01)

def html5_date_widget(extra_attrs=None):
    attrs = {'type': 'date'}
    if extra_attrs:
        attrs.update(extra_attrs)
    return forms.DateInput(format='%Y-%m-%d', attrs=attrs)

# ─────────────────────────────
#  EMPRESA
# ─────────────────────────────
class EmpresaForm(forms.ModelForm):

    socios = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    empresas_consorciadas = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Empresa
        fields = [
            'ruc', 'nombre', 'nombre_gerente', 'dni_gerente',
            'telefono', 'correo', 'correo_envio', 'observaciones',
            'socios',
            # campos de consorcio
            'es_consorcio', 'nombre_consorcio', 'tributador',
            'ruc_tributador', 'es_independiente', 'ruc_consorcio',
            'empresas_consorciadas', 'representante_legal',
            'dni_representante',
        ]
        widgets = {
            'ruc':              forms.TextInput(attrs={'placeholder': '11 dígitos'}),
            'telefono':         forms.TextInput(attrs={'placeholder': '9 dígitos (opcional)'}),
            'dni_gerente':      forms.TextInput(attrs={'placeholder': 'Solo números'}),
            'correo':           forms.EmailInput(attrs={'placeholder': 'correo@ejemplo.com (opcional)'}),
            'correo_envio':     forms.HiddenInput(),
            'observaciones':    forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Observaciones opcionales'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1) Aplica la clase form-control (o form-check-input en checkboxes)
        for name, field in self.fields.items():
            cls = 'form-control'
            if isinstance(field.widget, forms.CheckboxInput):
                cls = 'form-check-input'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} {cls}".strip()

        # 2) Lógica EIRL para socios
        nombre = self.data.get('nombre', self.initial.get('nombre', ''))
        usa_socios = not self._es_eirl(nombre)
        self.fields['socios'].required = usa_socios

        # 3) Campos que NUNCA son obligatorios
        for name in (
            'telefono', 'correo', 'correo_envio', 'observaciones',
            'nombre_consorcio', 'tributador', 'ruc_tributador',
            'ruc_consorcio', 'empresas_consorciadas',
            'representante_legal', 'dni_representante',
        ):
            if name in self.fields:
                self.fields[name].required = False

        

        is_consorcio = bool(self.data.get('es_consorcio'))

        usa_socios   = not self._es_eirl(nombre) and not is_consorcio
        self.fields['socios'].required = usa_socios
        for name in ('ruc', 'nombre', 'nombre_gerente', 'dni_gerente'):
            if name in self.fields:
                # si es consorcio → campo opcional; si no, obligatorio
                self.fields[name].required = not is_consorcio
        

    @staticmethod
    def _es_eirl(nombre: str) -> bool:
        nombre = (nombre or '').lower()
        return any(p in nombre for p in (
            'e.i.r.l', 'eirl',
            'empresa individual de responsabilidad limitada'
        ))

    def clean(self):
        cleaned = super().clean()

        if cleaned.get('es_consorcio'):
            for campo in ('ruc', 'dni_gerente', 'socios'):
                if campo in self._errors:
                    del self._errors[campo]

        # ——— Validación de socios SOLO si NO es Consorcio ———
        if not cleaned.get('es_consorcio'):
            nombre = cleaned.get('nombre', '')
            es_eirl = self._es_eirl(nombre)
            socios_txt = (cleaned.get('socios') or '').strip()

            if not es_eirl:
                if not socios_txt:
                    self.add_error('socios', 'Debe ingresar al menos un socio.')
                elif not suma_porcentajes(socios_txt):
                    self.add_error('socios', 'La suma de porcentajes debe ser exactamente 100 %.')
            else:
                cleaned['socios'] = ''
        else:
            cleaned['socios'] = ''

        # ——— Validación de los datos de consorcio ———
        if cleaned.get('es_consorcio'):
            if not cleaned.get('nombre_consorcio', '').strip():
                self.add_error('nombre_consorcio', 'Debe indicar el nombre del consorcio.')

            ruc_tributador = (cleaned.get('ruc_tributador') or '').strip()

            if not ruc_tributador:
                self.add_error('ruc_tributador', 'Debe indicar el RUC del tributador.')
            elif not re.match(r'^\d{11}$', ruc_tributador):
                self.add_error('ruc_tributador', 'El RUC del tributador debe tener exactamente 11 dígitos numéricos.')
            elif Empresa.objects.filter(ruc=ruc_tributador).exclude(id=self.instance.id).exists():
                self.add_error('ruc_tributador', 'Ya existe una empresa con este RUC.')
            else:
                # El RUC principal de la empresa será el RUC del tributador
                cleaned['ruc'] = ruc_tributador

            # si NO es independiente, valida empresas_consorciadas = 100%
            if not cleaned.get('es_independiente'):
                txt = (cleaned.get('empresas_consorciadas') or '').strip()
                if not txt:
                    self.add_error('empresas_consorciadas',
                                'Debe ingresar las empresas y porcentajes.')
                elif not suma_porcentajes(txt):
                    self.add_error('empresas_consorciadas',
                                'La suma de porcentajes debe ser exactamente 100 %.')
        else:
            # limpiar automáticamente si no es consorcio
            for fld in (
                'nombre_consorcio', 'tributador', 'ruc_tributador',
                'es_independiente', 'ruc_consorcio',
                'empresas_consorciadas', 'representante_legal',
                'dni_representante',
            ):
                cleaned[fld] = False if isinstance(self.fields[fld], forms.BooleanField) else ''

        return cleaned

    def clean_ruc(self):
        if self.cleaned_data.get('es_consorcio'):
            # Para consorcio, el RUC principal será el del tributador
            return (self.data.get('ruc_tributador') or '').strip()

        ruc = (self.cleaned_data.get('ruc') or '').strip()
        if not re.match(r'^\d{11}$', ruc):
            raise ValidationError('El RUC debe tener exactamente 11 dígitos numéricos.')
        if Empresa.objects.filter(ruc=ruc).exclude(id=self.instance.id).exists():
            raise ValidationError('Ya existe una empresa con este RUC.')
        return ruc

    def clean_telefono(self):
        tel = (self.cleaned_data.get('telefono') or '').strip()
        if tel and not re.match(r'^\d{9}$', tel):
            raise ValidationError('El número de teléfono debe tener exactamente 9 dígitos.')
        return tel

    def clean_dni_gerente(self):
        if self.cleaned_data.get('es_consorcio'):
            return self.cleaned_data.get('dni_gerente','')
        dni = self.cleaned_data['dni_gerente'].strip()
        if not dni.isdigit():
            raise ValidationError('El DNI/C.E. debe contener solo números.')
        return dni
    
    def clean_correo_envio(self):
        raw = (self.cleaned_data.get('correo_envio') or '').strip()
        if not raw:
            return ''

        validator = EmailValidator()
        correos = []

        for correo in re.split(r'[,\n;]+', raw):
            correo = correo.strip()
            if not correo:
                continue
            try:
                validator(correo)
            except ValidationError:
                raise ValidationError(f'Correo de envío inválido: {correo}')
            correos.append(correo)

        return ', '.join(correos)

    def save(self, commit=True):
        obj = super().save(commit=False)

        if obj.es_consorcio:
            obj.ruc = (obj.ruc_tributador or '').strip()

        if commit:
            obj.save()

        return obj


# ─────────────────────────────
#  CARTA FIANZA
# ─────────────────────────────
class CartaFianzaForm(forms.ModelForm):

    # Redefinimos el campo para poder aceptar “V”, “II”, etc.
    numero_adicional = forms.CharField(
        required=False,
        label='Número de adicional',
        help_text='Si es un adicional > 1, escríbalo en números romanos (II, III…) o arábigos (2, 3…).',
        widget=forms.TextInput(attrs={'class': 'form-control',
                                      'placeholder': 'I, II, III…'}),
        error_messages={
            'invalid': 'Ingrese un número entero o romano válido.'
        },
    )

    class Meta:
        model   = CartaFianza
        exclude = ['empresa']
        widgets = {
            'fecha_vencimiento':   html5_date_widget(),
            'tiene_consorcio':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_independiente':    forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'empresas_consorciadas': forms.HiddenInput(),   # se edita con JS
        }

    # ——— Personaliza atributos Bootstrap en todos los campos ———
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['fecha_vencimiento'].input_formats = ['%Y-%m-%d']

        for name, field in self.fields.items():
            attrs = field.widget.attrs
            # Aseguramos que la clave 'class' siempre existe (puede estar vacía)
            existing = attrs.get('class', '')
            if isinstance(field.widget, forms.CheckboxInput):
                # Concatenamos 'mt-1' al final
                attrs['class'] = f"{existing} mt-1".strip()
            else:
                # Aplicamos 'form-control', sin perder clases previas
                attrs['class'] = f"{existing} form-control".strip()

        # placeholders específicos
        self.fields['aseguradora_otro'].widget.attrs.update(
            {'placeholder': 'Ingrese la aseguradora'}
        )
        self.fields['afianzado'].widget.attrs.update(
            {'placeholder': 'Empresa / persona afianzada'}
        )

    # ——— VALIDACIÓN de “Número de adicional” ———
    def clean_numero_adicional(self):
        valor = (self.cleaned_data.get('numero_adicional') or '').strip()

        # campo vacío: se decide luego en clean()
        if valor == '':
            return None

        # si son solo dígitos → arábigo
        if valor.isdigit():
            return int(valor)

        # intentar convertir número romano
        try:
            return romano_a_entero(valor)
        except ValueError:
            raise ValidationError(
                'Ingrese un número romano válido (I, II, III...).'
            )

    # ——— VALIDACIÓN GLOBAL ———
    def clean(self):
        cleaned = super().clean()

        # -----------------------------------------------------------------
        # 1) Lógica de adicional
        # -----------------------------------------------------------------
        tipo = (cleaned.get('tipo_carta') or '').upper()
        num  = cleaned.get('numero_adicional')

        if 'ADICIONAL' in tipo:
            # si está vacío ⇒ por defecto 1
            if num is None:
                cleaned['numero_adicional'] = 1
        else:
            # si no es carta adicional, forzamos None
            cleaned['numero_adicional'] = None

        # -----------------------------------------------------------------
        # 2) Consorcio (bloques que ya tenías)
        # -----------------------------------------------------------------
        if cleaned.get('tiene_consorcio'):
            oblig = ['nombre_consorcio', 'empresas_consorciadas',
                     'representante_legal', 'dni_representante']
            for campo in oblig:
                if not cleaned.get(campo):
                    self.add_error(campo, 'Este campo es obligatorio si hay consorcio.')

            # validar suma de porcentajes
            raw = cleaned.get('empresas_consorciadas', '')
            matches = re.findall(r'\((\d+(?:\.\d+)?)%\)', raw)
            if matches and round(sum(float(p) for p in matches), 2) != 100.00:
                self.add_error('empresas_consorciadas',
                               'La suma de porcentajes debe ser exactamente 100 %.')

            # consorcio independiente → campos extra
            if cleaned.get('es_independiente'):
                for campo in ('tributador', 'ruc_tributador', 'ruc_consorcio'):
                    if not cleaned.get(campo):
                        self.add_error(
                            campo,
                            'Obligatorio cuando es independiente dentro del consorcio.'
                        )

        # -----------------------------------------------------------------
        # 3) Aseguradora “OTROS”
        # -----------------------------------------------------------------
        if cleaned.get('aseguradora') == 'OTROS' and not cleaned.get('aseguradora_otro'):
            self.add_error('aseguradora_otro', 'Debe ingresar la aseguradora.')

        return cleaned
class LiquidacionFianzaForm(forms.ModelForm):
    class Meta:
        model = LiquidacionFianza
        fields = ['monto_dev','aseguradora','fecha_dev','nro_fianza','documentos']
        widgets = {
            'fecha_dev': html5_date_widget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_dev'].input_formats = ['%Y-%m-%d']

# ─────────────────────────────
#  FIDEICOMISO (sin cambios)
# ─────────────────────────────




class DesembolsoForm(forms.ModelForm):
    class Meta:
        model  = Desembolso
        fields = ['tipo', 'fecha', 'monto']
        widgets = {
            'fecha': html5_date_widget({'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha'].input_formats = ['%Y-%m-%d']
        for f in self.fields.values():
            f.widget.attrs['class'] = f.widget.attrs.get('class', '') + ' form-control'

# ─────────────────────────────
#  FORMSET DE ARCHIVOS
# ─────────────────────────────
ArchivoAdjuntoFormSet = modelformset_factory(
    ArchivoAdjunto,
    fields=('archivo',),
    extra=0,
    can_delete=True
)

DesembolsoFormSet = forms.modelformset_factory(
    Desembolso,
    form     = DesembolsoForm,
    extra    = 0,
    can_delete = False
)

class CorreoFidForm(forms.ModelForm):
    class Meta:
        model  = CorreoFideicomiso
        fields = ('propietario', 'correo')
        widgets = {'propietario': forms.TextInput(attrs={'class':'form-control'}),
                   'correo':      forms.EmailInput(attrs={'class':'form-control'})}

CorreoFidFormSet = inlineformset_factory(
        Fideicomiso, CorreoFideicomiso,
        form=CorreoFidForm, extra=0, can_delete=True)

class AdelantoFidForm(forms.ModelForm):
    class Meta:
        model  = AdelantoFid
        fields = ('fecha', 'monto')
        widgets = {
            'fecha': html5_date_widget({'class': 'form-control'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha'].input_formats = ['%Y-%m-%d']

AdelantoFidFormSet = inlineformset_factory(
        Fideicomiso, AdelantoFid,
        form=AdelantoFidForm, extra=0, can_delete=True)

DocumentoFidFormSet = inlineformset_factory(
        Fideicomiso, DocumentoFid,
        fields=('categoria','archivo'),
        extra=0, can_delete=True)

# 2-B ▸ VALIDACIÓN EN FideicomisoForm  ──────────────────────────────
class FideicomisoForm(forms.ModelForm):
    class Meta:
        model = Fideicomiso
        exclude = ('empresa', 'resta_pendiente')   # "empresa" la fija la vista; "resta_pendiente" se calcula
        widgets = {
            'fecha_inicio'         : html5_date_widget({'class': 'form-control'}),
            'fecha_termino'        : html5_date_widget({'class': 'form-control'}),
            'deuda_total_moneda'   : forms.Select(attrs={'class': 'form-select'}),
            'deuda_total'          : forms.NumberInput(attrs={'class': 'form-control'}),
            'adelanto_directo_moneda'   : forms.Select(attrs={'class': 'form-select'}),
            'adelanto_directo_monto'    : forms.NumberInput(attrs={'class': 'form-control'}),
            'adelanto_materiales_moneda': forms.Select(attrs={'class': 'form-select'}),
            'adelanto_materiales_monto' : forms.NumberInput(attrs={'class': 'form-control'}),
            'monto_contrato_moneda': forms.Select(attrs={'class': 'form-select'}),
            'monto_contrato'       : forms.NumberInput(attrs={'class': 'form-control'}),
            'plazo_ejecucion'      : forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 12 meses'}),
            'entidad_ejecutora'    : forms.TextInput(attrs={'class': 'form-control'}),
            'entidad_fiduciaria'   : forms.TextInput(attrs={'class': 'form-control'}),
            'representante'        : forms.TextInput(attrs={'class': 'form-control'}),
            'residente_obra'       : forms.TextInput(attrs={'class': 'form-control'}),
            'estado_ejecucion'     : forms.TextInput(attrs={'class': 'form-control'}),
            'modalidad_ejecucion'  : forms.TextInput(attrs={'class': 'form-control'}),
            'tributador_nombre'    : forms.TextInput(attrs={'class': 'form-control'}),
            'tributador_banco'     : forms.TextInput(attrs={'class': 'form-control'}),
            'tributador_nro_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
            'tributador_nro_cci'   : forms.TextInput(attrs={'class': 'form-control'}),

            # ——— Consorcio (widgets básicos) ———
            'tiene_consorcio'      : forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'nombre_consorcio'     : forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del consorcio'}),
            'empresas_consorciadas': forms.HiddenInput(),   # se edita con JS
            'representante_legal'  : forms.TextInput(attrs={'class': 'form-control'}),
            'dni_representante'    : forms.TextInput(attrs={'class': 'form-control'}),
            'es_independiente'     : forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ruc_consorcio'        : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '11 dígitos'}),
            # ————————————————————————————————
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_inicio'].input_formats = ['%Y-%m-%d']
        self.fields['fecha_termino'].input_formats = ['%Y-%m-%d']
        # ─── Aplicar clases Bootstrap a todos los campos ───
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' form-check-input'
            else:
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' form-control'

    def clean(self):
        cleaned   = super().clean()

        # 1) Adelantos vs deuda
        deuda     = cleaned.get('deuda_total') or Decimal('0')
        adelantos = getattr(self, '_suma_adel', Decimal('0'))
        if deuda and adelantos > deuda:
            raise ValidationError("La suma de adelantos supera la deuda total.")
        cleaned['resta_pendiente'] = deuda - adelantos

        # 2) Consorcio: la suma debe ser 100 %
        if cleaned.get('tiene_consorcio'):
            txt = (cleaned.get('empresas_consorciadas') or '').strip()

            # Si no es independiente, exigimos la lista y el 100 %
            if not cleaned.get('es_independiente'):
                if not txt:
                    self.add_error('empresas_consorciadas',
                                'Debe ingresar las empresas y porcentajes.')
                elif not suma_porcentajes(txt):
                    self.add_error('empresas_consorciadas',
                                'La suma de porcentajes debe ser exactamente 100 %.')

            # Si es independiente, además pedimos RUC
            if cleaned.get('es_independiente') and not cleaned.get('ruc_consorcio'):
                self.add_error('ruc_consorcio', 'Obligatorio cuando el consorcio es independiente.')

        return cleaned




# ─────────────────────────────
#  FORMSET DE PAGOS
# ─────────────────────────────
class PagoEmpresaForm(forms.ModelForm):
    class Meta:
        model   = PagoEmpresa
        fields = [
            "moneda", "monto_total", "cancelado",
            "tipo_comprobante", "fecha_pago",
            "origen", "carta", "fideicomiso",
        ]
        widgets = {
            'fecha_pago': html5_date_widget({'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        cancelado   = cleaned.get('cancelado', False)
        monto_total = cleaned.get('monto_total') or Decimal('0')

        # Adelantos (igual que tenías)
        try:
            adelantos = json.loads(self.data.get('adelantos', '[]'))
        except ValueError:
            adelantos = []
        suma_adelantos = sum(
            Decimal(str(a.get('monto') or 0)).quantize(Decimal('0.01'))
            for a in adelantos
        )
        UMBRAL = Decimal('0.01')

        # 2) Reglas de origen (CARTA / FIDEI)
        origen = cleaned.get('origen')
        carta  = cleaned.get('carta')
        fidei  = cleaned.get('fideicomiso')

        # La empresa se fija en __init__ si se pasó por kwargs
        empresa = getattr(self.instance, 'empresa', None)

        if origen == 'CARTA':
            if not carta:
                self.add_error('carta', 'Selecciona la carta.')
            elif empresa and carta.empresa_id != empresa.id:
                self.add_error('carta', 'La carta seleccionada no pertenece a esta empresa.')
            # neutraliza el otro campo
            cleaned['fideicomiso'] = None

        elif origen == 'FIDEI':
            if not fidei:
                self.add_error('fideicomiso', 'Selecciona el fideicomiso.')
            elif empresa and fidei.empresa_id != empresa.id:
                self.add_error('fideicomiso', 'El fideicomiso seleccionado no pertenece a esta empresa.')
            cleaned['carta'] = None

        # 3) Consistencias con adelantos
        if suma_adelantos > monto_total:
            raise ValidationError('La suma de adelantos no puede superar el monto total.')

        if cancelado:
            if suma_adelantos and abs(suma_adelantos - monto_total) > UMBRAL:
                raise ValidationError('Cuando el pago está cancelado la suma de adelantos debe coincidir con el monto total.')
            if not cleaned.get('tipo_comprobante'):
                self.add_error('tipo_comprobante', 'Obligatorio cuando el pago está cancelado.')
            if not cleaned.get('fecha_pago'):
                self.add_error('fecha_pago', 'Obligatoria cuando el pago está cancelado.')

        return cleaned
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop("empresa", None)
        super().__init__(*args, **kwargs)
        self.fields['fecha_pago'].input_formats = ['%Y-%m-%d']

        # Ordena campos modernos (opcional)
        self.fields["origen"].label = "Origen del pago"
        self.fields["carta"].label = "Carta Fianza"
        self.fields["fideicomiso"].label = "Fideicomiso"

        # Limita queryset de selects si tenemos empresa
        if empresa is None and self.instance and self.instance.pk:
            empresa = self.instance.empresa
        if empresa:
            self.instance.empresa = empresa

        from .models import CartaFianza, Fideicomiso
        if empresa:
            self.fields["carta"].queryset = CartaFianza.objects.filter(empresa=empresa).order_by("-fecha_vencimiento")
            self.fields["fideicomiso"].queryset = Fideicomiso.objects.filter(empresa=empresa).order_by("-fecha_termino")
        else:
            self.fields["carta"].queryset = CartaFianza.objects.none()
            self.fields["fideicomiso"].queryset = Fideicomiso.objects.none()

# Adelantos: al menos uno si no está cancelado? O validación interna
AdelantoPagoFormSet = inlineformset_factory(
    PagoEmpresa, AdelantoPago,
    fields=('fecha','monto'), extra=1, can_delete=True
)

DocumentoPagoFormSet = inlineformset_factory(
    PagoEmpresa, DocumentoPago,
    fields=('archivo',), extra=1, can_delete=True
)