from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nucleo import permisos
from nucleo.models import Colaborador, Evidencia, Ocurrencia, Periodo
from datetime import date, timedelta

from nucleo.servicios import agenda, ejecucion, evidencias, kpi, parametros, presentacion, reglas_texto, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado


def _sin_perfil(request):
    return render(request, "nucleo/sin_perfil.html", status=403)


@login_required
def inicio(request):
    return redirect("hoy")


def _contexto_checklist(request, pestana):
    """Lo común a Mi día, Mi semana y Mi mes: de quién es la vista, su cumplimiento y los enlaces entre pestañas."""
    rol = permisos.rol_de(request.user)
    propia = permisos.colaborador_de(request.user)
    personas = sorted(Colaborador.objects.filter(activo=True, usuario__isnull=False), key=lambda c: (agenda.orden_de(c, reloj.hoy()), c.nombre))
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
        texto, clase = presentacion.etiqueta_semaforo(k.semaforo)
        cumplimiento = {"k": k, "etiqueta": texto, "clase": clase, "meta": parametros.entero("meta_cumplimiento")}
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
        "hay_anterior": agenda.primer_dia() is None or lunes - timedelta(days=3) >= agenda.primer_dia(),  # el viernes anterior ya es de un mes abierto
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
        "hay_anterior": agenda.primer_dia() is None or anterior >= agenda.primer_dia(),
        "datos": agenda.mes_de(c["elegida"], primero.year, primero.month, c["hoy"]) if c["elegida"] else None,
    })
    return render(request, "nucleo/mes.html", c)


@login_required
def en_construccion(request, titulo):
    return render(request, "nucleo/en_construccion.html", {"titulo": titulo})


ACCIONES = {"hecha", "recibida", "revisar", "devolver", "bloquear", "retomar", "comentar", "horas"}


@login_required
def detalle(request, pk):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    o = get_object_or_404(Ocurrencia.objects.select_related("tarea__proceso", "cargo_ejecuta", "cargo_revisa", "colaborador", "periodo"), pk=pk)
    return render(request, "nucleo/detalle.html", {
        "o": o, "hoy": reloj.hoy(), "acciones": ejecucion.acciones_disponibles(o, request.user), "historial": ejecucion.historial_de(o),
        "puede_horas": ejecucion.puede_registrar_horas(o, request.user), "ve_adjuntos": evidencias.puede_ver(request.user, o), "texto_adjuntos": evidencias.TEXTO, "puede_comentar": permisos.rol_de(request.user) in permisos.QUE_MARCAN and o.periodo.estado != "cerrado",
        "periodicidad": reglas_texto.describir(o.tarea.regla(), o.tarea.regla_franja), "atrasada": o.estado in ("pendiente", "devuelta", "bloqueada") and o.fecha_limite < reloj.hoy(),
        "dia_del_cierre": o.regla_copia.get("n") if o.regla_copia.get("tipo") == "CIERRE_DIA_HABIL" else None,
    })


@login_required
@require_POST
def ocurrencia_accion(request, pk, accion):
    if accion not in ACCIONES:
        raise Http404
    o = get_object_or_404(Ocurrencia.objects.select_related("periodo", "tarea"), pk=pk)
    try:
        if accion == "hecha":
            ejecucion.marcar_hecha(o, request.user, minutos_reales=ejecucion.parsear_horas(request.POST.get("horas", "")))
        elif accion == "horas":
            ejecucion.registrar_horas(o, request.user, ejecucion.parsear_horas(request.POST.get("horas", "")))
        elif accion == "recibida":
            ejecucion.marcar_recibida(o, request.user)
        elif accion == "comentar":
            ejecucion.comentar(o, request.user, request.POST.get("comentario", ""), request.FILES.get("archivo"))
        elif accion == "bloquear":
            ejecucion.marcar_bloqueada(o, request.user, request.POST.get("comentario", ""))
        elif accion == "retomar":
            ejecucion.retomar(o, request.user)
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


@login_required
def evidencia(request, pk):
    """Entrega un adjunto solo a quien puede verlo. PDF e imágenes se muestran; lo demás se descarga. Nunca se ejecuta nada del archivo."""
    ev = get_object_or_404(Evidencia.objects.select_related("ocurrencia"), pk=pk)
    try:
        ruta = evidencias.ruta_del_archivo(ev, request.user)
    except PermisoDenegado as e:
        return HttpResponseForbidden(str(e))
    except ErrorDeNegocio as e:
        raise Http404(str(e)) from None
    en_pantalla = evidencias.se_muestra_en_el_navegador(ev) and request.GET.get("descargar") != "1"
    r = FileResponse(open(ruta, "rb"), content_type=ev.tipo_contenido, as_attachment=not en_pantalla, filename=ev.nombre_original)
    r["X-Content-Type-Options"] = "nosniff"
    r["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"
    r["Cache-Control"] = "private, no-store"
    return r


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
