from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nucleo import permisos
from nucleo.models import Colaborador, Ocurrencia, Periodo
from nucleo.servicios import agenda, ejecucion, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado


def _sin_perfil(request):
    return render(request, "nucleo/sin_perfil.html", status=403)


@login_required
def inicio(request):
    return redirect("hoy")


@login_required
def hoy(request):
    rol = permisos.rol_de(request.user)
    if rol is None:
        return _sin_perfil(request)
    propia = permisos.colaborador_de(request.user)
    personas = list(Colaborador.objects.filter(activo=True, usuario__isnull=False))
    elegida = propia
    if request.GET.get("persona"):
        elegida = get_object_or_404(Colaborador, pk=request.GET["persona"], activo=True)
    elif propia is None and personas:
        elegida = personas[0]
    fecha = reloj.hoy()
    contexto = {
        "rol": rol, "personas": personas, "elegida": elegida, "hoy": fecha,
        "es_mia": elegida is not None and propia is not None and elegida.pk == propia.pk,
        "hay_mes_abierto": Periodo.objects.filter(estado="abierto").exists(),
        "agenda": agenda.agenda_de(elegida, fecha) if elegida else None,
        "por_revisar": agenda.por_revisar(request.user, fecha),
        "por_recibir": agenda.por_recibir(request.user, fecha),
    }
    return render(request, "nucleo/hoy.html", contexto)


ACCIONES = {"hecha", "recibida", "revisar", "devolver"}


@login_required
@require_POST
def ocurrencia_accion(request, pk, accion):
    if accion not in ACCIONES:
        raise Http404
    o = get_object_or_404(Ocurrencia.objects.select_related("periodo", "tarea"), pk=pk)
    try:
        if accion == "hecha":
            ejecucion.marcar_hecha(o, request.user)
        elif accion == "recibida":
            ejecucion.marcar_recibida(o, request.user)
        elif accion == "revisar":
            ejecucion.revisar(o, request.user)
        else:
            ejecucion.devolver(o, request.user, request.POST.get("comentario", ""))
        messages.success(request, f"Listo: {o.tarea.codigo}.")
    except PermisoDenegado as e:
        return HttpResponseForbidden(str(e))
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    destino = request.POST.get("siguiente", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse("hoy")
    return redirect(destino)


def acceso_rapido(request):
    """Entrar sin clave, SOLO en desarrollo local (settings.ACCESO_RAPIDO). En cualquier otro caso la ruta no existe."""
    if not settings.ACCESO_RAPIDO:
        raise Http404
    usuarios = get_user_model().objects.filter(is_active=True, groups__isnull=False).distinct().order_by("username")
    if request.method == "POST":
        u = get_object_or_404(usuarios, username=request.POST.get("usuario", ""))
        login(request, u, backend="nucleo.autenticacion.RespaldoConBloqueo")
        return redirect("hoy")
    return render(request, "nucleo/acceso_rapido.html", {"usuarios": [(u, permisos.rol_de(u)) for u in usuarios]})
