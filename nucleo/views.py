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
from datetime import date, timedelta

from nucleo.servicios import agenda, ejecucion, kpi, parametros, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado


def _sin_perfil(request):
    return render(request, "nucleo/sin_perfil.html", status=403)


@login_required
def inicio(request):
    return redirect("hoy")


ETIQUETAS_SEMAFORO = {
    "verde": ("Cumple", "ok"), "ambar": ("Bajo la meta", "warn"), "rojo": ("En riesgo", "red"),
    "muestra_insuficiente": ("Muestra insuficiente (menos de {minimo} tareas vencidas)", "grey"), "sin_datos": ("Sin datos", "grey"),
}


def _contexto_checklist(request, pestana):
    """Lo común a Mi día, Mi semana y Mi mes: de quién es la vista, su cumplimiento y los enlaces entre pestañas."""
    rol = permisos.rol_de(request.user)
    propia = permisos.colaborador_de(request.user)
    personas = list(Colaborador.objects.filter(activo=True, usuario__isnull=False))
    elegida = propia
    if request.GET.get("persona"):
        elegida = get_object_or_404(Colaborador, pk=request.GET["persona"], activo=True)
    elif propia is None and personas:
        elegida = personas[0]
    fecha = reloj.hoy()
    es_mia = elegida is not None and propia is not None and elegida.pk == propia.pk
    cumplimiento = None
    if elegida:
        k = kpi.de_persona(elegida, fecha)
        minimo = parametros.entero("minimo_muestra_semaforo")
        texto, clase = ETIQUETAS_SEMAFORO[k.semaforo]
        cumplimiento = {"k": k, "etiqueta": texto.format(minimo=minimo), "clase": clase, "meta": parametros.entero("meta_cumplimiento")}
    return {
        "rol": rol, "personas": personas, "elegida": elegida, "hoy": fecha, "es_mia": es_mia, "pestana": pestana,
        "persona_qs": "" if es_mia or elegida is None else f"persona={elegida.pk}", "cumplimiento": cumplimiento,
        "hay_mes_abierto": Periodo.objects.filter(estado="abierto").exists(),
    }


def _fecha_de(texto, por_defecto: date) -> date:
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return por_defecto


@login_required
def hoy(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    c = _contexto_checklist(request, "dia")
    c.update({
        "agenda": agenda.agenda_de(c["elegida"], c["hoy"]) if c["elegida"] else None,
        "por_revisar": agenda.por_revisar(request.user, c["hoy"]),
        "por_recibir": agenda.por_recibir(request.user, c["hoy"]),
    })
    return render(request, "nucleo/hoy.html", c)


@login_required
def semana(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    c = _contexto_checklist(request, "semana")
    referencia = _fecha_de(request.GET.get("fecha"), c["hoy"])
    lunes = referencia - timedelta(days=referencia.weekday())
    c.update({
        "dias": agenda.semana_de(c["elegida"], referencia, c["hoy"]) if c["elegida"] else [],
        "lunes": lunes, "viernes": lunes + timedelta(days=4),
        "fecha_anterior": (lunes - timedelta(days=7)).isoformat(), "fecha_siguiente": (lunes + timedelta(days=7)).isoformat(),
    })
    return render(request, "nucleo/semana.html", c)


@login_required
def mes(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    c = _contexto_checklist(request, "mes")
    try:
        anio, m = (int(x) for x in request.GET.get("mes", "").split("-"))
        primero = date(anio, m, 1)
    except ValueError:
        primero = c["hoy"].replace(day=1)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)
    c.update({
        "primero": primero, "mes_anterior": anterior.strftime("%Y-%m"), "mes_siguiente": siguiente.strftime("%Y-%m"),
        "datos": agenda.mes_de(c["elegida"], primero.year, primero.month, c["hoy"]) if c["elegida"] else None,
    })
    return render(request, "nucleo/mes.html", c)


@login_required
def en_construccion(request, titulo):
    return render(request, "nucleo/en_construccion.html", {"titulo": titulo})


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
