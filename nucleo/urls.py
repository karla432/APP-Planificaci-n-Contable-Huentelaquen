from django.contrib.auth import views as auth_views
from django.urls import path

from nucleo import views, views_checklist_cargos, views_informes
from nucleo.autenticacion import FormularioDeIngreso

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("checklist/dia/", views.hoy, name="hoy"),
    path("checklist/semana/", views.semana, name="semana"),
    path("checklist/mes/", views.mes, name="mes"),
    path("informes/panel/", views_informes.panel, name="informe_panel"),
    path("informes/cumplimiento/", views_informes.cumplimiento, name="informe_cumplimiento"),
    path("checklist/cargos/", views_checklist_cargos.cargos, name="checklist_cargos"),
    path("mantenedor/tareas/", views.en_construccion, {"titulo": "Mantenedor de tareas"}, name="mant_tareas"),
    path("mantenedor/procesos/", views.en_construccion, {"titulo": "Mantenedor de procesos"}, name="mant_procesos"),
    path("mantenedor/usuarios/", views.en_construccion, {"titulo": "Mantenedor de usuarios"}, name="mant_usuarios"),
    path("acceso-rapido/", views.acceso_rapido, name="acceso_rapido"),
    path("ocurrencias/<int:pk>/<str:accion>/", views.ocurrencia_accion, name="ocurrencia_accion"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="nucleo/login.html", authentication_form=FormularioDeIngreso, redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
