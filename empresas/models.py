import os
import re
import unicodedata
from django.db import models
from django.core.validators import RegexValidator, EmailValidator
from django.core.exceptions import ValidationError
from collections import defaultdict

from decimal import Decimal
from django.db.models import Sum

# ────────────────────────────────────────────────────────────
# Validadores
# ────────────────────────────────────────────────────────────
ruc_validator      = RegexValidator(r'^\d{11}$', 'El RUC debe tener exactamente 11 dígitos numéricos.')
telefono_validator = RegexValidator(r'^\d{9}$',  'El número de teléfono debe tener 9 dígitos.')
dni_validator      = RegexValidator(r'^\d+$',    'Solo se permiten números.')
numeros_validator  = RegexValidator(r'^\d+$',    'Este campo solo debe contener números.')

# ────────────────────────────────────────────────────────────
# Opciones
# ────────────────────────────────────────────────────────────

_ROMAN_MAP = [
    (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
    (100,  'C'), (90,  'XC'), (50,  'L'), (40,  'XL'),
    (10,   'X'), (9,   'IX'), (5,   'V'), (4,   'IV'), (1, 'I')
]

def entero_a_romano(n: int) -> str:
    if n <= 0:
        return str(n)
    res = ''
    for val, sym in _ROMAN_MAP:
        while n >= val:
            res += sym
            n -= val
    return res


ASEGURADORAS = [
    ('SECREX', 'SECREX'),
    ('INSUR', 'INSUR'),
    ('CRECER', 'CRECER'),
    ('AVLA',   'AVLA'),
    
    ('OTROS',  'OTROS'),
]

TIPOS_CARTA = [
    ('ADELANTO DE MATERIALES', 'ADELANTO DE MATERIALES'),
    ('ADELANTO DIRECTO',       'ADELANTO DIRECTO'),
    ('FIEL CUMPLIMIENTO',      'FIEL CUMPLIMIENTO'),
    ('FONDO_MI_VIVIENDA', 'FIEL CUMPLIENTO DE FONDO MI VIVIENDA'),
    ('FIEL CUMPLIMIENTO – ADICIONAL', 'FIEL CUMPLIMIENTO – ADICIONAL')
]

MONEDAS = [
    ('S/', 'Soles'),
    ('$',  'Dólares'),
    ('€',  'Euros'),
]
def _norm_text(value: str) -> str:
    value = (value or "").strip().upper()
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"\s+", " ", value)
    return value


def _split_empresas_consorciadas(texto: str) -> list[str]:
    """
    Convierte:
    'EMPRESA A (10%), EMPRESA B (90%)'
    o
    'EMPRESA A (10%)\\nEMPRESA B (90%)'
    en:
    ['EMPRESA A', 'EMPRESA B']
    """
    items = []
    for raw in re.split(r"\s*(?:,|;|\r?\n)+\s*", texto or ""):
        raw = raw.strip()
        if not raw:
            continue
        nombre = re.sub(r"\s*\((\d+(?:\.\d+)?)%\)\s*$", "", raw).strip(" -–—,")
        if nombre:
            items.append(nombre)
    return items


def _empresa_aliases(empresa) -> set[str]:
    valores = {
        empresa.ruc,
        empresa.nombre,
        empresa.nombre_consorcio,
        empresa.tributador,
        empresa.ruc_tributador,
        empresa.ruc_consorcio,
    }
    return {_norm_text(v) for v in valores if v}


def _carta_aliases(carta) -> set[str]:
    valores = {
        carta.afianzado,
        carta.nombre_consorcio,
        carta.tributador,
        carta.ruc_tributador,
        carta.ruc_consorcio,
    }

    if carta.empresa_id:
        valores.add(carta.empresa.ruc)
        valores.add(carta.empresa.nombre)
        valores.add(carta.empresa.nombre_consorcio)

    for item in _split_empresas_consorciadas(carta.empresas_consorciadas):
        valores.add(item)

    return {_norm_text(v) for v in valores if v}


def _empresa_calza_con_carta(empresa, carta) -> bool:
    return bool(_empresa_aliases(empresa) & _carta_aliases(carta))

def _fideicomiso_aliases(fidei) -> set[str]:
    valores = {
        fidei.nombre_consorcio,
        fidei.ruc_consorcio,
    }

    if fidei.empresa_id:
        valores.update({
            fidei.empresa.ruc,
            fidei.empresa.nombre,
            fidei.empresa.nombre_consorcio,
            fidei.empresa.tributador,
            fidei.empresa.ruc_tributador,
            fidei.empresa.ruc_consorcio,
        })

    for item in _split_empresas_consorciadas(fidei.empresas_consorciadas):
        valores.add(item)

    return {_norm_text(v) for v in valores if v}


def _empresa_calza_con_fideicomiso(empresa, fidei) -> bool:
    return bool(_empresa_aliases(empresa) & _fideicomiso_aliases(fidei))
# ────────────────────────────────────────────────────────────
# MODELO EMPRESA
# ────────────────────────────────────────────────────────────
class Empresa(models.Model):
    ruc            = models.CharField(max_length=11, unique=True,
                                      validators=[ruc_validator], verbose_name='RUC')
    nombre         = models.CharField(max_length=100, verbose_name='Nombre de la Empresa')
    nombre_gerente = models.CharField(max_length=100, verbose_name='Nombre del Gerente')
    dni_gerente    = models.CharField(max_length=15, validators=[dni_validator],
                                      verbose_name='DNI/C.E. del Gerente')
    telefono       = models.CharField(max_length=9, validators=[telefono_validator], blank=True, null=True,
                                      verbose_name='Número de Teléfono')
    correo         = models.EmailField(verbose_name='Correo Electrónico', blank=True, null=True,)

    # nuevo
    correo_envio = models.TextField(
        'Correos de envío',
        blank=True,
        null=True,
        help_text='Direcciones separadas por coma o punto y coma'
    )

    observaciones = models.TextField(
        'Observaciones',
        blank=True,
        default='',
        help_text='Notas opcionales de la empresa o consorcio'
    )
    
    socios = models.TextField(
        blank=True,
        verbose_name='Socios (% y DNI/C.E.)',
        help_text='Se completa automáticamente desde el formulario'
    )
    es_consorcio          = models.BooleanField(default=False)
    nombre_consorcio      = models.CharField(max_length=200, blank=True)
    tributador            = models.CharField(max_length=200, blank=True)
    ruc_tributador        = models.CharField(max_length=11, blank=True)
    es_independiente      = models.BooleanField(default=False)
    ruc_consorcio         = models.CharField(max_length=11, blank=True)
    empresas_consorciadas = models.TextField(blank=True,
                                help_text="Lista de empresas + % (suma=100%)")
    representante_legal   = models.CharField(max_length=200, blank=True)
    dni_representante     = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.nombre} ({self.ruc})"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_empresa_con_cartas(self)
        sync_empresa_con_fideicomisos(self)

    def delete(self, *args, **kwargs):
        # Eliminar archivos de cartas fianza
        for carta in self.cartas_fianza.all():
            for archivo in carta.archivos.all():
                archivo.archivo.delete(save=False)
                archivo.delete()
        # Eliminar archivos de fideicomisos
        for fidei in self.fideicomisos.all():
            for archivo in fidei.archivos.all():
                archivo.archivo.delete(save=False)
                archivo.delete()
        super().delete(*args, **kwargs)

# ────────────────────────────────────────────────────────────
# MODELO ARCHIVO
# ────────────────────────────────────────────────────────────
class ArchivoAdjunto(models.Model):
    archivo       = models.FileField(upload_to='archivos_adjunto/')
    carta         = models.ForeignKey('CartaFianza', on_delete=models.CASCADE,
                                      null=True, blank=True, related_name='archivos')
    fideicomiso   = models.ForeignKey('Fideicomiso', on_delete=models.CASCADE,
                                      null=True, blank=True, related_name='archivos')

    def __str__(self):
        return self.archivo.name.split('/')[-1]

# ────────────────────────────────────────────────────────────
# MODELO CARTA FIANZA
# ────────────────────────────────────────────────────────────
class CartaFianza(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='cartas_fianza',
        verbose_name='Empresa'
    )
    empresas_relacionadas = models.ManyToManyField(
        Empresa,
        blank=True,
        related_name='cartas_fianza_relacionadas',
        verbose_name='Empresas relacionadas por consorcio'
    )

    aseguradora      = models.CharField(max_length=30, choices=ASEGURADORAS,
                                         verbose_name='Aseguradora')
    aseguradora_otro = models.CharField('Especifique la aseguradora',
                                         max_length=100, blank=True, null=True)
    
    numero_adicional = models.PositiveSmallIntegerField(
        blank=True, null=True,
        verbose_name="Número de adicional",
        help_text="Si es un adicional > 1, escríbelo en números romanos (II, III…)"
    )

    numero_fianza    = models.CharField(max_length=20, verbose_name='Número de Fianza')
    tipo_carta       = models.CharField(max_length=30, choices=TIPOS_CARTA, verbose_name='Tipo de Carta')
    moneda           = models.CharField(max_length=3, choices=MONEDAS, verbose_name='Moneda')
    monto            = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Monto')
    plazo_meses      = models.PositiveIntegerField(verbose_name='Plazo (Meses)')
    plazo_dias       = models.PositiveIntegerField(verbose_name='Plazo (Días)')
    fecha_vencimiento = models.DateField(verbose_name='Fecha de Vencimiento')

    entidad          = models.CharField(max_length=100, verbose_name='Entidad/Beneficiario')
    afianzado        = models.CharField('Afianzado', max_length=150, blank=True, null=True)

    # ── Consorcio ───────────────────────────────────────────
    tiene_consorcio      = models.BooleanField(default=False, verbose_name='¿Tiene Consorcio?')

    # datos originales del consorcio (ya existentes)
    nombre_consorcio     = models.CharField(max_length=100, blank=True, verbose_name='Nombre del Consorcio')
    empresas_consorciadas = models.TextField(blank=True, verbose_name='Empresas Consorciadas y Porcentaje')
    representante_legal  = models.CharField(max_length=100, blank=True, verbose_name='Representante Legal')
    dni_representante    = models.CharField(max_length=15, blank=True,
                                            validators=[dni_validator], verbose_name='DNI/C.E. del Representante')

    # ── Independiente dentro del consorcio ────────────────
    es_independiente = models.BooleanField(default=False, verbose_name='¿Es Independiente?')
    tributador       = models.CharField('Tributador', max_length=150, blank=True, null=True)
    ruc_tributador   = models.CharField('RUC Tributador', max_length=11,
                                        validators=[ruc_validator], blank=True, null=True)
    ruc_consorcio    = models.CharField('RUC Consorcio', max_length=11,
                                        validators=[ruc_validator], blank=True, null=True)
    liquidada = models.BooleanField(default=False, verbose_name="¿Liquidada?")

    # ── Validaciones de negocio ───────────────────────────
    def clean(self):
        # Aseguradora "OTROS" → nombre obligatorio
        if self.aseguradora == 'OTROS' and not self.aseguradora_otro:
            raise ValidationError({'aseguradora_otro': 'Debe especificar la aseguradora.'})

        # Consorcio e independiente → tres campos obligatorios
        if self.tiene_consorcio and self.es_independiente:
            faltantes = [f for f in ('tributador', 'ruc_tributador', 'ruc_consorcio')
                         if not getattr(self, f)]
            if faltantes:
                raise ValidationError('Complete Tributador, RUC Tributador y RUC Consorcio.')

    def __str__(self):
        return f"Fianza {self.numero_fianza} - {self.empresa.nombre}"
    
    def pertenece_a_empresa(self, empresa) -> bool:
        empresa_id = getattr(empresa, "id", empresa)
        if not empresa_id:
            return False
        return (
            self.empresa_id == empresa_id
            or self.empresas_relacionadas.filter(id=empresa_id).exists()
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_carta_fianza_relaciones(self)

    def delete(self, *args, **kwargs):
        for archivo in self.archivos.all():
            if archivo.archivo and os.path.isfile(archivo.archivo.path):
                os.remove(archivo.archivo.path)
        super().delete(*args, **kwargs)

    def tipo_completo(self) -> str:
        
        if 'ADICIONAL' in (self.tipo_carta or '').upper():
            suf = self.numero_adicional or 1
            # si el usuario guardó 1 explícitamente también queremos el 'I'
            suf_romano = entero_a_romano(int(suf))
            return f'{self.tipo_carta} {suf_romano}'
        return self.tipo_carta

def sync_carta_fianza_relaciones(carta):
    if not carta.pk:
        return

    relacionados_ids = set()

    # siempre incluir la empresa dueña
    if carta.empresa_id:
        relacionados_ids.add(carta.empresa_id)

    # si no tiene consorcio, limpiar todo y dejar solo la dueña
    if not carta.tiene_consorcio:
        carta.empresas_relacionadas.set(relacionados_ids)
        return

    empresas = Empresa.objects.all().only(
        "id", "ruc", "nombre", "nombre_consorcio",
        "tributador", "ruc_tributador", "ruc_consorcio"
    )

    for empresa in empresas:
        if carta.empresa_id == empresa.id or _empresa_calza_con_carta(empresa, carta):
            relacionados_ids.add(empresa.id)

    carta.empresas_relacionadas.set(relacionados_ids)


def sync_empresa_con_cartas(empresa):
    if not empresa.pk:
        return

    cartas = CartaFianza.objects.filter(tiene_consorcio=True).select_related("empresa")

    for carta in cartas:
        if carta.empresa_id == empresa.id or _empresa_calza_con_carta(empresa, carta):
            carta.empresas_relacionadas.add(empresa)
        else:
            carta.empresas_relacionadas.remove(empresa)

def sync_fideicomiso_relaciones(fidei):
    if not fidei.pk:
        return

    relacionados_ids = set()

    # siempre incluir la empresa dueña
    if fidei.empresa_id:
        relacionados_ids.add(fidei.empresa_id)

    # si no tiene consorcio, dejar solo la dueña
    if not fidei.tiene_consorcio:
        fidei.empresas_relacionadas.set(relacionados_ids)
        return

    empresas = Empresa.objects.all().only(
        "id", "ruc", "nombre", "nombre_consorcio",
        "tributador", "ruc_tributador", "ruc_consorcio"
    )

    for empresa in empresas:
        if fidei.empresa_id == empresa.id or _empresa_calza_con_fideicomiso(empresa, fidei):
            relacionados_ids.add(empresa.id)

    fidei.empresas_relacionadas.set(relacionados_ids)


def sync_empresa_con_fideicomisos(empresa):
    if not empresa.pk:
        return

    fideicomisos = Fideicomiso.objects.filter(
        tiene_consorcio=True
    ).select_related("empresa")

    for fidei in fideicomisos:
        if fidei.empresa_id == empresa.id or _empresa_calza_con_fideicomiso(empresa, fidei):
            fidei.empresas_relacionadas.add(empresa)
        else:
            fidei.empresas_relacionadas.remove(empresa)

class LiquidacionFianza(models.Model):
    carta       = models.OneToOneField(
        'CartaFianza',
        on_delete=models.CASCADE,
        related_name='liquidacion',
        verbose_name='Carta Fianza'
    )
    monto_dev   = models.DecimalField(
        "Monto total de devolución",
        max_digits=12, decimal_places=2
    )
    aseguradora = models.CharField(
        max_length=30,
        choices=ASEGURADORAS,
        verbose_name='Aseguradora'
    )
    fecha_dev   = models.DateField("Fecha de devolución")
    nro_fianza  = models.CharField("Nº de Fianza", max_length=20)
    documentos  = models.FileField(
        upload_to='liquidacion_fianzas/',
        verbose_name='Documentos de liquidación',
        blank=True, null=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Liquidación de Carta {self.carta.numero_fianza}"


# ────────────────────────────────────────────────────────────
# MODELO FIDEICOMISO
# ────────────────────────────────────────────────────────────
class Fideicomiso(models.Model):
    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='fideicomisos'
    )

    empresas_relacionadas = models.ManyToManyField(
        Empresa,
        blank=True,
        related_name='fideicomisos_relacionados',
        verbose_name='Empresas relacionadas por consorcio'
    )

    

    # ── Datos del TRIBUTADOR ────────────────────────────────
    tributador_nombre     = models.CharField(max_length=100, verbose_name='Nombre del Tributador')
    tributador_banco      = models.CharField(max_length=100, verbose_name='Banco')
    tributador_nro_cuenta = models.CharField(max_length=30,  verbose_name='Nro. de Cuenta')
    tributador_nro_cci    = models.CharField(max_length=30,  verbose_name='Nro. de Cuenta CCI')

    # ── Datos principales ───────────────────────────────────
    entidad_ejecutora  = models.CharField(max_length=100)
    entidad_fiduciaria = models.CharField(max_length=100)
    representante      = models.CharField(max_length=100)

    adelanto_directo_moneda    = models.CharField(max_length=3, choices=MONEDAS, default='S/')
    adelanto_directo_monto     = models.DecimalField(max_digits=12, decimal_places=2)
    adelanto_materiales_moneda = models.CharField(max_length=3, choices=MONEDAS, default='S/')
    adelanto_materiales_monto  = models.DecimalField(max_digits=12, decimal_places=2)

    residente_obra      = models.CharField(max_length=100)
    estado_ejecucion    = models.CharField(max_length=100)
    modalidad_ejecucion = models.CharField(max_length=100)

    monto_contrato_moneda = models.CharField(max_length=3, choices=MONEDAS, default='S/')
    monto_contrato        = models.DecimalField(max_digits=12, decimal_places=2)

    plazo_ejecucion = models.CharField(max_length=50)

    fecha_inicio  = models.DateField()
    fecha_termino = models.DateField()

    deuda_total     = models.DecimalField(max_digits=12, decimal_places=2,
                                          blank=True, null=True)
    deuda_total_moneda =models.CharField(
        max_length=3,
        choices=MONEDAS,
        default='S/',
        verbose_name="Moneda de los pagos"
    )
    resta_pendiente = models.DecimalField(max_digits=12, decimal_places=2,
                                          blank=True, null=True)
    
    # ── Consorcio ────────────────────────────────────────
    tiene_consorcio        = models.BooleanField(default=False)
    nombre_consorcio       = models.CharField(max_length=100, blank=True)
    empresas_consorciadas  = models.TextField(blank=True)
    representante_legal    = models.CharField(max_length=100, blank=True)
    dni_representante      = models.CharField(max_length=30, blank=True)
    es_independiente       = models.BooleanField(default=False)
    ruc_consorcio          = models.CharField(max_length=11, blank=True)
    # ────────────────────────────────────────────────────────
    
    # ayuda para plantillas
    @property
    def suma_adelantos(self):
        from django.db.models import Sum
        return self.adelantos.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    
    @property
    def deuda_restante(self):
        if self.deuda_total is not None:
            return self.deuda_total - self.suma_adelantos
        return None

    

    # ────────────────────────────────────────────────────────
    # PROPIEDADES DE CÁLCULO
    # ────────────────────────────────────────────────────────
    # ► Adelanto DIRECTO
    @property
    def directo_con_retencion(self):
        """96 % del adelanto directo"""
        return (self.adelanto_directo_monto or 0) * Decimal('0.96')

    @property
    def directo_desembolsado(self):
        """Suma de desembolsos ya registrados (tipo DIRECTO)"""
        total = (self.desembolsos
                 .filter(tipo='DIRECTO')
                 .aggregate(t=Sum('monto'))['t']) or Decimal('0')
        return total

    @property
    def directo_restante(self):
        """Monto pendiente por desembolsar del adelanto directo"""
        return self.directo_con_retencion - self.directo_desembolsado

    # ► Adelanto MATERIALES
    @property
    def materiales_con_retencion(self):
        """96 % del adelanto de materiales"""
        return (self.adelanto_materiales_monto or 0) * Decimal('0.96')

    @property
    def materiales_desembolsado(self):
        """Suma de desembolsos ya registrados (tipo MATERIALES)"""
        total = (self.desembolsos
                 .filter(tipo='MATERIALES')
                 .aggregate(t=Sum('monto'))['t']) or Decimal('0')
        return total

    @property
    def materiales_restante(self):
        """Monto pendiente por desembolsar del adelanto de materiales"""
        return self.materiales_con_retencion - self.materiales_desembolsado
    
    @property
    def documentos_por_categoria(self) -> dict[str, list["DocumentoFid"]]:
        """
        Devuelve un diccionario
        { 'Desembolsos mensuales': [doc1, doc2, …],
          'Factura sustentación'  : [doc3, …], … }
        listo para usar en la plantilla.
        """
        # 1) tabla "código" → "etiqueta legible"
        label_of = dict(DocumentoFid.CAT_CHOICES)

        # 2) agrupar en memoria (una sola consulta)
        grupos = defaultdict(list)
        for doc in self.documentos.all():
            grupos[label_of.get(doc.categoria, doc.categoria)].append(doc)

        # 3) ordena alfabéticamente por etiqueta (opcional)
        return dict(sorted(grupos.items()))
    # ────────────────────────────────────────────────────────

    def __str__(self):
        return f"Fideicomiso - {self.entidad_fiduciaria} ({self.empresa.nombre})"
    
    def pertenece_a_empresa(self, empresa) -> bool:
        empresa_id = getattr(empresa, "id", empresa)
        if not empresa_id:
            return False
        return (
            self.empresa_id == empresa_id
            or self.empresas_relacionadas.filter(id=empresa_id).exists()
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_fideicomiso_relaciones(self)

    def delete(self, *args, **kwargs):
        # eliminar archivos físicos
        for archivo in self.archivos.all():
            if archivo.archivo and os.path.isfile(archivo.archivo.path):
                os.remove(archivo.archivo.path)
        super().delete(*args, **kwargs)

class CorreoFideicomiso(models.Model):
    fideicomiso = models.ForeignKey("Fideicomiso",
                                    on_delete=models.CASCADE,
                                    related_name="correos")
    propietario = models.CharField("Propietario", max_length=120, blank=True)
    correo      = models.EmailField("Correo")

    def __str__(self):
        return f"{self.propietario or ''} <{self.correo}>"

class DocumentoFid(models.Model):
    CAT_CHOICES = [
        ('desembolso',        'Desembolsos mensuales'),
        ('curva_s',           'Curva S'),
        ('fact_sustentacion', 'Factura sustentación'),
        ('fact_fiduciaria',   'Factura fiduciaria'),
        ('fact_control',      'Factura supervisión-control'),
        ('sust_mensual',      'Sustentos mensuales'),
        ('sust_obra',         'Sustentos de obra'),
        ('carta_lib',         'Cartas de liberación'),
        ('cronograma',        'Cronograma de pago'),
    ]
    fideicomiso = models.ForeignKey("Fideicomiso",
                                    on_delete=models.CASCADE,
                                    related_name="documentos")
    categoria   = models.CharField(max_length=20, choices=CAT_CHOICES)
    archivo     = models.FileField(upload_to="fideicomiso_docs/")

    @property
    def filename(self):
        import os
        return os.path.basename(self.archivo.name)
    
    

class AdelantoFid(models.Model):
    fideicomiso = models.ForeignKey("Fideicomiso",
                                    on_delete=models.CASCADE,
                                    related_name="adelantos")
    fecha       = models.DateField(blank=True, null=True)
    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    

    def __str__(self):
        return f"{self.fecha or '—'} – {self.monto}"


class Desembolso(models.Model):
    TIPOS = [
        ('DIRECTO',     'Directo'),
        ('MATERIALES',  'Materiales'),
    ]

    fideicomiso = models.ForeignKey(
        Fideicomiso,
        on_delete=models.CASCADE,
        related_name='desembolsos'
    )
    tipo   = models.CharField(max_length=11, choices=TIPOS)
    fecha  = models.DateField()
    monto  = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.monto} ({self.fecha})"
    


class PagoEmpresa(models.Model):
    ORIGEN_CHOICES = (
    ("CARTA", "Cartas Fianza"),
    ("FIDEI", "Fideicomisos"),
    )

    COMPROBANTES = [
        ('FACTURA', 'Factura'),
        ('RECIBO',  'Recibo por honorarios'),
        ('NINGUNO','Ninguno'),
    ]
    origen = models.CharField(max_length=5, choices=ORIGEN_CHOICES, default="CARTA")
    carta = models.ForeignKey(
        "CartaFianza", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pagos"
    )
    fideicomiso = models.ForeignKey(
        "Fideicomiso", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pagos"
    )
    empresa           = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='pagos',
        verbose_name='Empresa'
    )
    moneda            = models.CharField(
        max_length=3,
        choices=MONEDAS,
        verbose_name='Moneda'
    )
    monto_total       = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Monto total'
    )
    cancelado         = models.BooleanField(
        default=False,
        verbose_name='¿Cancelado?'
    )
    tipo_comprobante  = models.CharField(
        max_length=20,
        choices=COMPROBANTES,
        blank=True,
        verbose_name='Tipo de comprobante'
    )
    fecha_pago        = models.DateField(
        blank=True,
        null=True,
        verbose_name='Fecha de pago'
    )
    created_at        = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de registro'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pago a Empresa'
        verbose_name_plural = 'Pagos a Empresa'

    def clean(self):
        # 1) Reglas de "cancelado"
        if self.cancelado:
            if not self.tipo_comprobante:
                raise ValidationError({'tipo_comprobante': 'Debe indicar el tipo de comprobante.'})
            if not self.fecha_pago:
                raise ValidationError({'fecha_pago': 'Debe indicar la fecha de pago.'})

        # 2) Coherencia de origen / vínculo
        if self.origen == "CARTA":
            if not self.carta or self.fideicomiso:
                raise ValidationError("Selecciona una Carta Fianza (y no un Fideicomiso) para un pago de origen CARTA.")
            if self.carta and not self.carta.pertenece_a_empresa(self.empresa):
                raise ValidationError("La carta seleccionada no pertenece ni está relacionada a esta empresa.")
        elif self.origen == "FIDEI":
            if not self.fideicomiso or self.carta:
                raise ValidationError("Selecciona un Fideicomiso (y no una Carta) para un pago de origen FIDEI.")
            if self.fideicomiso and not self.fideicomiso.pertenece_a_empresa(self.empresa):
                raise ValidationError("El fideicomiso seleccionado no pertenece ni está relacionado a esta empresa.")
        else:
            raise ValidationError("Origen inválido.")

        # Llama a clean() de la superclase al final
        super().clean()

    def __str__(self):
        return f"{self.empresa.nombre} – {self.moneda}{self.monto_total} ({'Pagado' if self.cancelado else 'Pendiente'})"

class AdelantoPago(models.Model):
    pago              = models.ForeignKey(
        PagoEmpresa,
        on_delete=models.CASCADE,
        related_name='adelantos',
        verbose_name='Pago'
    )
    monto             = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Monto del adelanto'
    )
    fecha             = models.DateField(
        verbose_name='Fecha del adelanto'
    )

    class Meta:
        ordering = ['fecha']
        verbose_name = 'Adelanto de Pago'
        verbose_name_plural = 'Adelantos de Pago'

    def __str__(self):
        return f"{self.pago.empresa.nombre}: {self.monto} el {self.fecha}"


class DocumentoPago(models.Model):
    pago              = models.ForeignKey(
        PagoEmpresa,
        on_delete=models.CASCADE,
        related_name='documentos',
        verbose_name='Pago'
    )
    archivo           = models.FileField(
        upload_to='pagos_adjuntos/',
        verbose_name='Documento de pago'
    )

    class Meta:
        verbose_name = 'Documento de Pago'
        verbose_name_plural = 'Documentos de Pago'

    def __str__(self):
        return self.archivo.name.split('/')[-1]


class AvisoVencimiento(models.Model):
    carta = models.ForeignKey("CartaFianza", on_delete=models.CASCADE, related_name="avisos")
    days_before = models.PositiveSmallIntegerField()  # 15..20
    sent_at = models.DateTimeField(auto_now_add=True)
    recipients = models.TextField(blank=True)  # snapshot de correos destino (coma-separados)
    subject = models.CharField(max_length=200, default="¡TU FIANZA ESTA A PUNTO DE VENCER!")

    class Meta:
        unique_together = (("carta", "days_before"),)  # evita reenvíos duplicados por día/aviso
        ordering = ("-sent_at",)

    def __str__(self):
        return f"Aviso {self.days_before}d antes - {self.carta.numero_fianza}"