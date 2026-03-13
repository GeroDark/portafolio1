from django.urls import path

from . import views

app_name = "propuestas"

urlpatterns = [
    path("buscar/", views.buscar_propuestas, name="buscar"),
    path("nueva/carta-fianza/", views.crear_propuesta_cf, name="crear_cf"),
    path("nueva/fideicomiso/", views.crear_propuesta_fd, name="crear_fd"),
    path("calendario/", views.calendario_propuestas, name="calendario"),
    path("<int:pk>/", views.detalle_propuesta, name="detalle"),
    path("<int:pk>/editar/", views.editar_propuesta, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar_propuesta, name="eliminar"),
    path("ajax/empresas/", views.ajax_buscar_empresas, name="ajax_empresas"),
    path("ajax/cartas-fianza/", views.ajax_buscar_cartas_fianza, name="ajax_cartas"),
    path("ajax/fideicomisos/", views.ajax_buscar_fideicomisos, name="ajax_fideicomisos"),
    path("<int:pk>/documentos/subir/", views.subir_documento_propuesta, name="subir_documento"),
    path(
        "<int:pk>/documentos/<int:doc_id>/eliminar/",
        views.eliminar_documento_propuesta,
        name="eliminar_documento",
    ),
]