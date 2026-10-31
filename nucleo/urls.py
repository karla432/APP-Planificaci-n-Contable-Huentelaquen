from django.contrib.auth import views as auth_views
from django.urls import path

from nucleo import views, views_checklist_cargos, views_apertura, views_informes, views_mantenedor
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
    path("checklist/cargos/", views_checklist_cargos.cargos, name="checklist_cargos"),
    path("cierre/abrir/", views_apertura.abrir_mes, name="abrir_mes"),
    path("mantenedor/tareas/", views_mantenedor.tareas, name="mant_tareas"),
    path("mantenedor/tareas/nueva/", views_mantenedor.tarea_nueva, name="mant_tarea_nueva"),
    path("mantenedor/tareas/<int:pk>/", views_mantenedor.tarea_editar, name="mant_tarea_editar"),
    path("mantenedor/procesos/", views_mantenedor.procesos, name="mant_procesos"),
    path("mantenedor/usuarios/", views_mantenedor.usuarios, name="mant_usuarios"),
    path("mantenedor/usuarios/nuevo/", views_mantenedor.usuario_nuevo, name="mant_usuario_nuevo"),
    path("mantenedor/usuarios/<int:pk>/", views_mantenedor.usuario_editar, name="mant_usuario_editar"),
    path("acceso-rapido/", views.acceso_rapido, name="acceso_rapido"),
    path("tareas/<int:pk>/", views.detalle, name="detalle_ocurrencia"),
    path("ocurrencias/<int:pk>/<str:accion>/", views.ocurrencia_accion, name="ocurrencia_accion"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="nucleo/login.html", authentication_form=FormularioDeIngreso, redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
