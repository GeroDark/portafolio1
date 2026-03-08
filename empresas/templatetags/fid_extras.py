from django import template, forms
register = template.Library()

@register.filter
def filename(value):
    """devuelve el último elemento del path 'carpeta/archivo.pdf' → 'archivo.pdf'"""
    return value.name.split('/')[-1]

@register.filter
def add_class(field, css):
    if isinstance(field, forms.BoundField):
        field.field.widget.attrs['class'] = \
            f"{field.field.widget.attrs.get('class','')} {css}"
    return field
