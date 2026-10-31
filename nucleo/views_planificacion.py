"""Planificación: la estructura de tres niveles (proceso → tarea → subtarea) como árbol y como tabla, con filtros y exportación a Excel."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from nucleo import permisos
from nucleo.models import ESTADOS_PLAN, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import auditoria, estructura, excel_masivo, reloj, vista_planificacion
from nucleo.views_mantenedor import XLSX, _prohibido
from nucleo.views_informes import _sin_perfil


@login_required
def planificacion(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    f = vista_planificacion.desde_get(request.GET)
    arbol = vista_planificacion.construir(f)
    vista = "tabla" if request.GET.get("vista") == "tabla" else "arbol"
    etapas = estructura.etapas()
    return render(request, "nucleo/planificacion.html", {
        "f": f, "vista": vista, "arbol": arbol, "filas": vista_planificacion.aplanar(arbol) if vista == "tabla" else [], "procesos": Proceso.objects.all(), "estados": ESTADOS_PLAN,
        "n_procesos": len(arbol), "n_tareas": sum(len(n.tareas) for n in arbol), "n_subtareas": sum(n.n_subtareas for n in arbol),
        "etapas": etapas, "hay_dependencias": any(e.numero > 1 for e in etapas),
        "puede_editar": permisos.rol_de(request.user) in (permisos.GERENTE, permisos.JEFATURA), "consulta": request.GET.urlencode(),
    })


@login_required
def planificacion_exportar(request):
    if permisos.rol_de(request.user) not in (permisos.GERENTE, permisos.JEFATURA):
        return _prohibido(request, "Solo el Gerente y la Jefatura exportan la planificación.")
    filas = vista_planificacion.aplanar(vista_planificacion.construir(vista_planificacion.desde_get(request.GET)))
    auditoria.registrar("planificacion.exportada", usuario=request.user, entidad="Proceso", despues={"filas": len(filas)})
    r = HttpResponse(excel_masivo.exportar_planificacion(filas), content_type=XLSX)
    r["Content-Disposition"] = f'attachment; filename="planificacion_{reloj.hoy():%Y%m%d}.xlsx"'
    r["Cache-Control"] = "no-store"
    return r
