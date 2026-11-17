"""Pantalla del segundo factor: dar de alta la aplicación de códigos (primera vez) y escribir el código al ingresar."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from nucleo.servicios import segundo_factor
from nucleo.servicios.errores import ErrorDeNegocio


@login_required
def segundo_factor_vista(request):
    usuario = request.user
    if not segundo_factor.exige(usuario):
        return redirect("hoy")
    sf = segundo_factor.de(usuario) or segundo_factor.crear(usuario, visible_en_pantalla=True)
    if request.method == "POST":
        try:
            if segundo_factor.verificar(usuario, request.POST.get("codigo", "")):
                request.session[segundo_factor.CLAVE_DE_SESION] = True
                destino = request.POST.get("siguiente", "")
                return redirect(destino if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}) else reverse("hoy"))
            messages.error(request, "Ese código no es válido. Revisa que el reloj de tu teléfono esté en hora y escribe el código vigente.")
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
    mostrar = sf.visible_en_pantalla and not sf.confirmado
    return render(request, "nucleo/segundo_factor.html", {
        "solo_2fa": True, "mostrar_clave": mostrar, "clave": segundo_factor.clave_legible(sf) if mostrar else "", "uri": segundo_factor.uri(sf) if mostrar else "",
        "qr": segundo_factor.qr_svg(sf) if mostrar else "", "siguiente": request.GET.get("siguiente", ""), "confirmado": sf.confirmado,
    })


@login_required
def clave_cambiada(request):
    from nucleo.servicios import auditoria
    auditoria.registrar("cuenta.clave_cambiada", usuario=request.user, entidad="Usuario", entidad_id=request.user.pk)
    messages.success(request, "Tu clave quedó cambiada.")
    return redirect("hoy")
