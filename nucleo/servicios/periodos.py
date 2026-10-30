"""Apertura de mes: genera las ocurrencias del período a partir de las reglas de las tareas.

Un período M reúne las diarias y semanales del mes M y el cierre del mes M−1 (vence en los primeros días de M).
- `vista_previa` no escribe nada. `abrir_mes` es idempotente: una tarea que ya tiene ocurrencias en el período no se vuelve a
  generar (así un cambio posterior en la tarea no reescribe el pasado: rige desde el período siguiente).
- Cada ocurrencia copia el responsable y la regla vigentes al generarse.
- Si a una tarea no se le puede generar todo el mes (sin responsable, regla incompleta…) no se genera nada de ella y se avisa;
  al corregirlo, volver a abrir el mes completa lo que faltaba.
"""
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from nucleo.models import Anio, Asignacion, Ocurrencia, Periodo, Tarea
from nucleo.servicios import auditoria, parametros
from nucleo.servicios.errores import ErrorDeNegocio
from nucleo.servicios.feriados import calendario_confirmado
from nucleo.servicios.recurrencia import ReglaIncompleta, ReglaInvalida, fechas_limite


@dataclass
class Aviso:
    tipo: str  # sin_responsable / varias_personas / requiere_revision / sin_regla / regla_incompleta / regla_invalida
    tarea: Tarea
    detalle: str


@dataclass
class ItemOcurrencia:
    tarea: Tarea
    fecha: date
    colaborador: object  # Colaborador o None (cargos externos)


@dataclass
class VistaPreviaMes:
    anio: int
    mes: int
    inicio_medicion: date | None
    ocurrencias: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    ya_existian: int = 0


@dataclass
class Resultado:
    periodo: Periodo
    creadas: int
    ya_existian: int
    avisos: list


def _regla_a_dict(regla) -> dict:
    return {"tipo": regla.tipo, "dia_semana": regla.dia_semana, "n": regla.n, "dia": regla.dia, "meses": list(regla.meses), "ajuste": regla.ajuste}


def vista_previa(anio: int, mes: int, inicio_medicion: date | None = None) -> VistaPreviaMes:
    if not Anio.objects.filter(anio=anio, estado="abierto").exists():
        raise ErrorDeNegocio(f"El año {anio} no está abierto: confirma los feriados y ábrelo antes de abrir un mes.")
    periodo = Periodo.objects.filter(anio=anio, mes=mes).first()
    if periodo and periodo.estado == "cerrado":
        raise ErrorDeNegocio(f"El período {mes:02d}-{anio} está cerrado; reabrirlo exige rol Gerente y un motivo.")
    inicio = periodo.inicio_medicion if periodo and periodo.inicio_medicion else inicio_medicion
    vp = VistaPreviaMes(anio, mes, inicio)

    cal = calendario_confirmado()
    min_dias = parametros.entero("min_dias_habiles_d7_d10")
    vigentes: dict[int, list] = {}
    for a in Asignacion.objects.select_related("colaborador").filter(colaborador__activo=True):
        vigentes.setdefault(a.cargo_id, []).append(a)
    ya = {}
    if periodo:
        for tarea_id in Ocurrencia.objects.filter(periodo=periodo).values_list("tarea_id", flat=True):
            ya[tarea_id] = ya.get(tarea_id, 0) + 1

    for t in Tarea.objects.filter(activa=True).select_related("cargo_ejecuta", "cargo_revisa", "proceso"):
        if t.pk in ya:
            vp.ya_existian += ya[t.pk]
            continue
        if t.requiere_revision:
            vp.avisos.append(Aviso("requiere_revision", t, t.motivo_revision or "Marcada para revisión."))
            continue
        if not t.regla_tipo:
            vp.avisos.append(Aviso("sin_regla", t, "La tarea no tiene regla de recurrencia."))
            continue
        try:
            fechas = fechas_limite(t.regla(), anio, mes, cal, min_dias_habiles_d7_d10=min_dias, inicio_medicion=inicio)
        except ReglaIncompleta as e:
            vp.avisos.append(Aviso("regla_incompleta", t, str(e)))
            continue
        except (ReglaInvalida, ValueError) as e:
            vp.avisos.append(Aviso("regla_invalida", t, str(e)))
            continue

        items, problema = [], None
        for f in fechas:
            if t.cargo_ejecuta.es_externo:
                items.append(ItemOcurrencia(t, f, None))
                continue
            personas = [a.colaborador for a in vigentes.get(t.cargo_ejecuta_id, []) if a.desde <= f and (a.hasta is None or a.hasta >= f)]
            if not personas:
                problema = Aviso("sin_responsable", t, f"El cargo «{t.cargo_ejecuta}» no tiene persona vigente el {f:%d-%m-%Y}.")
                break
            if len(personas) > 1:
                problema = Aviso("varias_personas", t, f"El cargo «{t.cargo_ejecuta}» tiene más de una persona vigente el {f:%d-%m-%Y}.")
                break
            items.append(ItemOcurrencia(t, f, personas[0]))
        if problema:
            vp.avisos.append(problema)
        else:
            vp.ocurrencias.extend(items)
    vp.ocurrencias.sort(key=lambda i: (i.fecha, i.tarea.codigo))
    return vp


@transaction.atomic
def abrir_mes(anio: int, mes: int, usuario, inicio_medicion: date | None = None) -> Resultado:
    vp = vista_previa(anio, mes, inicio_medicion)
    periodo, _ = Periodo.objects.get_or_create(anio=anio, mes=mes, defaults={"inicio_medicion": vp.inicio_medicion})
    Ocurrencia.objects.bulk_create([
        Ocurrencia(
            tarea=i.tarea, periodo=periodo, fecha_limite=i.fecha, cargo_ejecuta=i.tarea.cargo_ejecuta, colaborador=i.colaborador,
            cargo_revisa=i.tarea.cargo_revisa, regla_copia=_regla_a_dict(i.tarea.regla()),
            tipo_marca="RECIBIDA" if i.tarea.cargo_ejecuta.es_externo else "HECHA",
        )
        for i in vp.ocurrencias
    ])
    res = Resultado(periodo, len(vp.ocurrencias), vp.ya_existian, vp.avisos)
    auditoria.registrar(
        "periodo.abierto", usuario=usuario, entidad="Periodo", entidad_id=f"{mes:02d}-{anio}",
        despues={"creadas": res.creadas, "ya_existian": res.ya_existian, "avisos": len(res.avisos), "inicio_medicion": str(vp.inicio_medicion) if vp.inicio_medicion else None},
    )
    return res
