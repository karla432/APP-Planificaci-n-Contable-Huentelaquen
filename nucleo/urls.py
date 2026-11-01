from django.contrib.auth import views as auth_views
from django.urls import path

from nucleo import views, views_apertura, views_checklist_cargos, views_informes, views_mantenedor, views_planificacion
from nucleo.autenticacion import FormularioDeIngreso

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("checklist/dia/", views.hoy, name="hoy"),
    path("checklist/semana/", views.semana, name="semana"),
    path("checklist/mes/", views.mes, name="mes"),
    path("informes/panel/", views_informes.panel, name="informe_panel"),
    path("informes/cumplimiento/", views_informes.cumplimiento, name="informe_cumplimiento"),
    path("informes/tablero/", views_informes.tablero, name="informe_tablero"),
    path("informes/cronograma/", views_informes.cronograma, name="informe_cronograma"),
    path("informes/carga/", views_informes.carga_del_equipo, name="informe_carga"),
    path("informes/matriz/", views_informes.matriz_del_cierre, name="informe_matriz"),
    path("informes/matriz/exportar/", views_informes.matriz_exportar, name="informe_matriz_exportar"),
    path("checklist/cargos/", views_checklist_cargos.cargos, name="checklist_cargos"),
    path("planificacion/", views_planificacion.planificacion, name="planificacion"),
    path("planificacion/exportar/", views_planificacion.planificacion_exportar, name="planificacion_exportar"),
    path("cierre/abrir/", views_apertura.abrir_mes, name="abrir_mes"),
    path("mantenedor/tareas/", views_mantenedor.tareas, name="mant_tareas"),
    path("mantenedor/tareas/exportar/", views_mantenedor.tareas_exportar, name="mant_tareas_exportar"),
    path("mantenedor/tareas/cargar/", views_mantenedor.tareas_cargar, name="mant_tareas_cargar"),
    path("mantenedor/tareas/nueva/", views_mantenedor.tarea_nueva, name="mant_tarea_nueva"),
    path("mantenedor/tareas/<int:pk>/", views_mantenedor.tarea_editar, name="mant_tarea_editar"),
    path("mantenedor/procesos/", views_mantenedor.procesos, name="mant_procesos"),
    path("mantenedor/procesos/<int:pk>/", views_mantenedor.proceso_detalle, name="mant_proceso_detalle"),
    path("mantenedor/procesos/exportar/", views_mantenedor.procesos_exportar, name="mant_procesos_exportar"),
    path("mantenedor/procesos/cargar/", views_mantenedor.procesos_cargar, name="mant_procesos_cargar"),
    path("mantenedor/usuarios/", views_mantenedor.usuarios, name="mant_usuarios"),
    path("mantenedor/usuarios/nuevo/", views_mantenedor.usuario_nuevo, name="mant_usuario_nuevo"),
    path("mantenedor/usuarios/<int:pk>/", views_mantenedor.usuario_editar, name="mant_usuario_editar"),
    path("acceso-rapido/", views.acceso_rapido, name="acceso_rapido"),
    path("tareas/<int:pk>/", views.detalle, name="detalle_ocurrencia"),
    path("evidencias/<int:pk>/", views.evidencia, name="evidencia"),
    path("ocurrencias/<int:pk>/<str:accion>/", views.ocurrencia_accion, name="ocurrencia_accion"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="nucleo/login.html", authentication_form=FormularioDeIngreso, redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
