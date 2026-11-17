"""Falla cerrada: quien debe usar segundo factor no ve nada de la aplicación hasta verificar su código (solo la pantalla del código y salir)."""
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from nucleo.servicios import segundo_factor


class SegundoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and not request.session.get(segundo_factor.CLAVE_DE_SESION) and segundo_factor.exige(usuario):
            libres = (reverse("segundo_factor"), reverse("logout"), settings.STATIC_URL)
            if not request.path.startswith(libres):
                return redirect(f"{reverse('segundo_factor')}?siguiente={quote(request.get_full_path())}")
        return self.get_response(request)
