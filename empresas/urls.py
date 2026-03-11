from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve as static_serve

from . import views
from django.contrib.auth.views import LogoutView



# ───────── mini-vista para servir /media/ con SAMEORIGIN ─────────
def media_pdf(request, path):
    """
    Devuelve ficheros de MEDIA permitiendo <iframe>.
    Sólo se usa en DEBUG; en producción lo hace Nginx/Apache.
    """
    response = static_serve(request, path, document_root=settings.MEDIA_ROOT)
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


urlpatterns = [
    # ─── página inicial ───────────────────────────────────────────
    path("", views.home, name="home"),

    # ─── autenticación ───────────────────────────────────────────
    path('login/', views.google_login, name='login'),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),

    # ─── búsqueda y calendario ───────────────────────────────────
    path("buscar/",                views.buscar_empresa,     name="buscar_empresa"),
    path("empresa/autocomplete/",  views.empresa_autocomplete, name="empresa_autocomplete"),
    path("calendario/",            views.calendario_fianzas, name="calendario_fianzas"),
    path('carta/<int:fianza_id>/detalle/',   views.carta_detalle,   name='carta_detalle'),
    path('carta/<int:fianza_id>/archivos/',  views.carta_archivos,  name='carta_archivos'),
    path('fideicomiso/<int:fideicomiso_id>/detalle/', views.fideicomiso_detalle, name='fideicomiso_detalle'),
    path('fideicomiso/<int:fideicomiso_id>/documentos/', views.fideicomiso_documentos, name='fideicomiso_documentos'),

    # ─── cartas fianza ───────────────────────────────────────────
    
    path("empresas/<int:empresa_id>/agregar_carta/", views.agregar_carta_fianza, name="agregar_carta_fianza"),
    path("carta/<int:fianza_id>/editar/",   views.editar_carta_fianza,   name="editar_carta_fianza"),
    path("carta/<int:fianza_id>/eliminar/", views.eliminar_carta_fianza, name="eliminar_carta_fianza"),
    path(
      'carta-fianza/<int:fianza_id>/liquidar/',
      views.liquidar_carta,
      name='liquidar_carta'
    ),

    # ─── empresas ────────────────────────────────────────────────
    path("registrar/",                           views.registrar_empresa,  name="registrar_empresa"),
    path("empresas/",                            views.listar_empresas,    name="listar_empresas"),
    path("empresas/editar/<int:empresa_id>/",    views.editar_empresa,     name="editar_empresa"),
    path("empresas/eliminar/<int:empresa_id>/",  views.eliminar_empresa,   name="eliminar_empresa"),

    # ─── fideicomisos y desembolsos ──────────────────────────────
    path("empresa/<int:empresa_id>/fideicomiso/agregar/", views.agregar_fideicomiso,   name="agregar_fideicomiso"),
    path("fideicomiso/<int:fideicomiso_id>/editar/",      views.editar_fideicomiso,    name="editar_fideicomiso"),
    path("fideicomiso/<int:fideicomiso_id>/eliminar/",    views.eliminar_fideicomiso,  name="eliminar_fideicomiso"),
    path("fideicomiso/<int:fideicomiso_id>/desembolso/agregar/", views.agregar_desembolso, name="agregar_desembolso"),

    path('empresas/<int:empresa_id>/pago/nuevo/',
     views.nuevo_pago_empresa,
     name='nuevo_pago_empresa'),
    path(
        'empresas/pago/<int:pago_id>/editar/',
        views.editar_pago_empresa,
        name='editar_pago_empresa'
        ),
    path(
        'empresa/<int:empresa_id>/pago/',
        views.agregar_pago_empresa,
        name='agregar_pago_empresa'
    ),
    path(
        'empresas/pago/<int:pago_id>/eliminar/',
        views.eliminar_pago_empresa,
        name='eliminar_pago_empresa'
    ),
    path("probar-aviso/", views.probar_aviso, name="probar_aviso"),
    path("preview-aviso/<int:fianza_id>/", views.preview_aviso, name="preview_aviso"),
  
    
]

# ─── servir /media/ en desarrollo ────────────────────────────────
if settings.DEBUG:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", media_pdf, name="media_pdf"),
    ]
