from django.contrib.auth import views as auth_views
from django.urls import path

from nucleo import views
from nucleo.autenticacion import FormularioDeIngreso

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="nucleo/login.html", authentication_form=FormularioDeIngreso, redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]
