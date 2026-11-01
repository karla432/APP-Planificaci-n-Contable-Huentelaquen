"""Cierre mensual → Abrir mes: confirmar feriados, abrir el año, ver qué se va a generar y abrir el mes.

Solo Gerente y administrador del sistema. El permiso se valida aquí; las reglas de negocio (año abierto, feriados confirmados,
mes idempotente) viven en los servicios y sus mensajes se muestran tal cual.
"""
import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from nucleo import permisos
from nucleo.models import Anio, Feriado, Periodo
from nucleo.servicios import feriados, kpi, periodos, reglas_texto, reloj
from nucleo.servicios.errores import ErrorDeNegocio
from nucleo.views_mantenedor import con_roles

ABRE_MESES = (permisos.GERENTE, permisos.ADMIN_SISTEMA)
ETIQUETAS_AVISO = {
    "sin_responsable": "Sin persona responsable", "varias_personas": "Más de una persona en el cargo",
    "requiere_revision": "Requiere revisión", "sin_regla": "Sin regla de periodicidad",
    "regla_incompleta": "Regla incompleta", "regla_invalida": "Regla inválida",
}
ORDEN_TIPOS = ["DIARIA_HABIL", "SEMANAL", "CIERRE_DIA_HABIL", "CIERRE_HITO", "DIA_FIJO", "FIN_DE_MES", "MESES", "EVENTO"]
TIPOS_DE_FERIADO = [("legal", "Legal"), ("irrenunciable", "Irrenunciable"), ("decretado", "Decretado"), ("regional", "Regional")]


def _mes_elegido(texto: str | None, hoy: date) -> date:
    try:
        anio, mes = (int(x) for x in (texto or "").split("-"))
        return date(anio, mes, 1)
    except ValueError:
        return hoy.replace(day=1)


def _resumen_por_regla(vp) -> list[dict]:
    """Cuántas tareas y ocurrencias se generan por cada forma de periodicidad, en palabras simples."""
    grupos: dict[str, dict] = {}
    for item in vp.ocurrencias:
        regla = item.tarea.regla()
        texto = reglas_texto.describir(regla)
        g = grupos.setdefault(texto, {"texto": texto, "tareas": set(), "ocurrencias": 0, "orden": (ORDEN_TIPOS.index(regla.tipo), regla.n or 0, texto)})
        g["tareas"].add(item.tarea.pk)
        g["ocurrencias"] += 1
    filas = sorted(grupos.values(), key=lambda g: g["orden"])
    return [{"texto": g["texto"], "tareas": len(g["tareas"]), "ocurrencias": g["ocurrencias"]} for g in filas]


def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto or "")
    except ValueError:
        return None


def _accion(request, primero: date):
    """Ejecuta la acción pedida. Devuelve el mensaje de éxito; los errores de negocio los atrapa la vista."""
    accion, anio, mes = request.POST.get("accion"), primero.year, primero.month
    if accion == "cargar_feriados":
        n = feriados.cargar_propuesta(anio)
        return f"Se cargaron {n} feriados de {anio}. Revísalos y confírmalos." if n else f"Los feriados de {anio} ya estaban cargados."
    if accion == "confirmar_feriados":
        return f"Se confirmaron {feriados.confirmar_anio(anio, request.user)} feriados de {anio}."
    if accion == "agregar_feriado":
        fecha, nombre, tipo = _fecha(request.POST.get("fecha")), request.POST.get("nombre", "").strip(), request.POST.get("tipo", "")
        if fecha is None or fecha.year != anio:
            raise ErrorDeNegocio(f"Indica una fecha de {anio}.")
        if not nombre or tipo not in dict(TIPOS_DE_FERIADO):
            raise ErrorDeNegocio("Indica el nombre y el tipo del feriado.")
        feriados.agregar_o_editar(fecha, nombre, tipo, request.user)
        return f"Se agregó «{nombre}» ({fecha:%d-%m-%Y}). Queda sin confirmar hasta que lo confirmes."
    if accion == "abrir_anio":
        feriados.abrir_anio(anio, request.user)
        return f"Año {anio} abierto: ya se pueden abrir sus meses."
    if accion == "abrir_mes":
        inicio = None
        if request.POST.get("inicio_medicion"):
            inicio = _fecha(request.POST["inicio_medicion"])
            if inicio is None or (inicio.year, inicio.month) != (anio, mes):
                raise ErrorDeNegocio("La fecha de inicio de la medición debe estar dentro del mes que se abre.")
        res = periodos.abrir_mes(anio, mes, request.user, inicio)
        texto = f"Mes {mes:02d}-{anio} abierto: {res.creadas} ocurrencias nuevas; {res.ya_existian} ya existían."
        if res.pausadas or res.reasignadas:
            texto += f" Por la semana del cierre: {res.pausadas} se pausaron y {res.reasignadas} las hace otro cargo."
        return texto + (f" {len(res.avisos)} tarea(s) quedaron sin generar: revisa los avisos." if res.avisos else "")
    raise ErrorDeNegocio("Acción desconocida.")


@con_roles(*ABRE_MESES)
def abrir_mes(request):
    hoy = reloj.hoy()
    primero = _mes_elegido(request.POST.get("mes") or request.GET.get("mes"), hoy)
    destino = f"{request.path}?mes={primero:%Y-%m}"
    if request.method == "POST":
        try:
            messages.success(request, _accion(request, primero))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        return redirect(destino)

    anio, mes = primero.year, primero.month
    ferias = list(Feriado.objects.filter(fecha__year=anio))
    sin_confirmar = sum(not f.confirmado for f in ferias)
    anio_abierto = Anio.objects.filter(anio=anio, estado="abierto").exists()
    periodo = Periodo.objects.filter(anio=anio, mes=mes).first()
    vp = problema = None
    if anio_abierto:
        try:
            vp = periodos.vista_previa(anio, mes)
        except ErrorDeNegocio as e:
            problema = str(e)
    return render(request, "nucleo/abrir_mes.html", {
        "primero": primero, "nombre_mes": f"{reglas_texto.MESES[mes - 1]} {anio}", "anio": anio, "mes_param": f"{primero:%Y-%m}",
        "mes_anterior": (primero - timedelta(days=1)).replace(day=1).strftime("%Y-%m"),
        "mes_siguiente": (primero + timedelta(days=32)).replace(day=1).strftime("%Y-%m"),
        "feriados": ferias, "sin_confirmar": sin_confirmar, "hay_feriados": bool(ferias), "anio_abierto": anio_abierto,
        "periodo": periodo, "vp": vp, "problema": problema,
        "resumen": _resumen_por_regla(vp) if vp else [], "avisos": [(ETIQUETAS_AVISO.get(a.tipo, a.tipo), a) for a in vp.avisos] if vp else [],
        "hitos": [(etiqueta, f, kpi.descripciones_del_mes(anio, mes).get(f, "")) for etiqueta, f in kpi.hitos_del_mes(anio, mes)] if anio_abierto else [],
        "ultimo_dia": date(anio, mes, calendar.monthrange(anio, mes)[1]), "tipos_feriado": TIPOS_DE_FERIADO,
    })
