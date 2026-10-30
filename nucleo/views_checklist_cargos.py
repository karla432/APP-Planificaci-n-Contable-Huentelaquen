"""Check List por cargo y responsable. Visible para todo el equipo, solo lectura."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from nucleo import permisos
from nucleo.models import Asignacion, Cargo, Ocurrencia, Tarea
from nucleo.servicios import kpi, reglas_texto, reloj
from nucleo.views_informes import _mes_elegido, _navegacion, _sin_perfil


@login_required
def cargos(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    c = {"hoy": hoy, "periodo": periodo, **_navegacion(primero)}
    if periodo is None:
        return render(request, "nucleo/checklist_cargos.html", c)

    responsables: dict[int, list[str]] = {}
    for a in Asignacion.objects.filter(desde__lte=hoy).exclude(hasta__lt=hoy).select_related("colaborador"):
        responsables.setdefault(a.cargo_id, []).append(a.colaborador.nombre)
    filas = []
    for cargo in Cargo.objects.filter(activo=True):
        ocs = list(Ocurrencia.objects.filter(periodo=periodo, cargo_ejecuta=cargo).exclude(estado=Ocurrencia.NO_APLICA))
        if not ocs and not responsables.get(cargo.pk):
            continue
        filas.append({
            "cargo": cargo, "responsables": ", ".join(responsables.get(cargo.pk, [])) or "—", "total": len(ocs),
            "hechas": sum(o.estado in kpi.HECHAS for o in ocs),
            "atrasadas": sum(o.estado in ("pendiente", "devuelta") and o.fecha_limite < hoy for o in ocs),
        })
    c["filas"] = filas

    if request.GET.get("cargo"):
        cargo = get_object_or_404(Cargo, pk=request.GET["cargo"])
        ocs = Ocurrencia.objects.filter(periodo=periodo, cargo_ejecuta=cargo).select_related("tarea__proceso", "colaborador").order_by("fecha_limite", "tarea__codigo")
        for o in ocs:
            o.periodicidad = reglas_texto.describir(o.tarea.regla(), o.tarea.regla_franja)
            o.pendiente = o.estado in ("pendiente", "devuelta")
            o.atrasada = o.pendiente and o.fecha_limite < hoy
        c.update({"detalle_cargo": cargo, "detalle": list(ocs), "detalle_responsables": responsables.get(cargo.pk, [])})
    return render(request, "nucleo/checklist_cargos.html", c)
