"""Excel «Planificación vigente»: todo lo que tiene la app, para revisarlo y, si se corrige, volver a cargarlo (Mantenedor → Tareas → Cargar Excel).

Hojas: Cómo leer · Plan vigente (una tarea por fila, con los códigos de la app) · Carga por persona y día (un mes, DH00 a DH10) · Procesos · Desactivadas.
El archivo vuelve a leerse con `plan2.leer_plan_vigente`: el código de cada fila identifica su tarea, aunque se corrija el texto.
"""
import io

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from nucleo.models import Proceso, Tarea
from nucleo.servicios import excel_masivo

ROJO = PatternFill("solid", start_color="FF8C0A2B", end_color="FF8C0A2B")
AMBAR = PatternFill("solid", start_color="FFFFF3CD", end_color="FFFFF3CD")
ROSA = PatternFill("solid", start_color="FFF8D7DA", end_color="FFF8D7DA")
VERDE = PatternFill("solid", start_color="FFD1E7DD", end_color="FFD1E7DD")
MODOS = {"igual": "Mantiene", "pausar": "Pausa", "fuera": "Fuera del equipo contable", "reasignar": "Reasigna"}
AL_TERMINAR = {"al_dia": "Se pone al día (registro acumulado)", "retoma": "Se retoma sin recuperar", "": ""}
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
COLUMNAS = ["Código", "Proceso", "Tarea principal", "Subtarea", "Responsable (ejecuta)", "Revisa", "Periodicidad", "Cuándo", "Empieza (día hábil)", "Horas por ejecución",
            "Horas por día hábil (cierre)", "Horas por día de la semana", "En las semanas del cierre", "Al terminar el cierre", "Predecesoras (códigos)", "Tipo de control",
            "Cambio respecto del plan anterior", "Justificación", "Por revisar", "Observación (referencia normativa)"]
ANCHOS = [15, 26, 30, 62, 20, 16, 16, 26, 11, 11, 30, 24, 22, 26, 36, 22, 28, 50, 36, 40]
LEYENDA = [
    ("Planificación vigente en la app · Hacienda Huentelauquén", True),
    ("Es lo que hoy tiene la app. Son horas ESTIMADAS. Si corriges algo en «Plan vigente», puedes volver a cargar este archivo en Mantenedor → Tareas → Cargar Excel: la app te muestra qué cambiaría antes de guardar.", False),
    ("", False),
    ("Hojas", True),
    ("Plan vigente: las tareas activas, una por fila, ordenadas por proceso y código. El código identifica la tarea: no lo cambies.", False),
    ("Carga por persona y día: las horas del mes de DH00 a DH10 contra la jornada (9 h de lunes a jueves, 5 h el viernes) y el techo de planificación.", False),
    ("Procesos: los procesos con su código y cuántas tareas tienen.", False),
    ("Desactivadas: tareas que ya no se hacen (no se borran; quedan como historial).", False),
    ("", False),
    ("Reglas vigentes", True),
    ("DH08, DH09 y DH10 son días hábiles (reportes listos, Gerente General y Directorio). DH00 es el último día hábil del mes anterior. Las semanas del cierre van de DH01 a DH10.", False),
    ("La revisión va dentro de las horas de quien ejecuta: no suma carga a quien revisa.", False),
    ("Techo de planificación: 90 % de la jornada de DH00 a DH06, 80 % DH07, 75 % DH08, 85 % DH09 y 95 % DH10. Ámbar = usa la reserva; rojo = pasa de la jornada.", False),
]


def _horas_dh(t) -> str:
    if not t.horas_dh:
        return ""
    return " · ".join(f"DH{int(k):02d} {v:g}" for k, v in sorted(t.horas_dh.items(), key=lambda kv: int(kv[0])))


def _horas_semana(t) -> str:
    if not t.horas_semana:
        return ""
    return " · ".join(f"{DIAS[int(k)]} {v:g}" for k, v in sorted(t.horas_semana.items(), key=lambda kv: int(kv[0])))


def _encabezado(hoja, fila, titulos, anchos):
    for i, (t, a) in enumerate(zip(titulos, anchos), start=1):
        c = hoja.cell(row=fila, column=i, value=t)
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFFFF"), ROJO, Alignment(wrap_text=True, vertical="center")
        hoja.column_dimensions[get_column_letter(i)].width = a
    hoja.row_dimensions[fila].height = 32


def _poner(hoja, fila, col, v, ajuste=False):
    c = excel_masivo._poner(hoja, fila, col, v)  # un texto que empiece con = + - @ no se vuelve fórmula
    c.alignment = Alignment(wrap_text=ajuste, vertical="top")
    return c


def exportar(anio: int, mes: int) -> bytes:
    wb = openpyxl.Workbook()
    h = wb.active
    h.title = "Cómo leer"
    for i, (t, negrita) in enumerate(LEYENDA, start=1):
        c = h.cell(row=i, column=1, value=t)
        c.font, c.alignment = Font(bold=negrita, size=13 if i == 1 else 11), Alignment(wrap_text=True, vertical="top")
    h.column_dimensions["A"].width = 150

    p = wb.create_sheet("Plan vigente")
    _encabezado(p, 1, COLUMNAS, ANCHOS)
    tareas = Tarea.objects.filter(activa=True).select_related("proceso", "cargo_ejecuta", "cargo_revisa").prefetch_related("predecesoras").order_by("proceso__orden", "padre__numero", "numero")
    for n, t in enumerate(tareas, start=2):
        per, cua = excel_masivo.texto_de_periodicidad(t)
        valores = [t.codigo, f"{t.proceso.codigo} · {t.proceso.nombre}", t.tarea_principal, t.subtarea, t.cargo_ejecuta.nombre, excel_masivo._revisa(t), per, cua,
                   "" if t.dh_inicio is None else f"DH{t.dh_inicio:02d}", None if t.minutos_estimados is None else round(t.minutos_estimados / 60, 4), _horas_dh(t), _horas_semana(t),
                   MODOS.get(t.modo_cierre, ""), AL_TERMINAR.get(t.al_terminar_cierre, ""), ", ".join(sorted(x.codigo for x in t.predecesoras.all())), t.tipo_control, t.cambio_plan,
                   t.justificacion, t.motivo_revision if t.requiere_revision else "", t.referencia_normativa]
        for col, v in enumerate(valores, start=1):
            _poner(p, n, col, v, ajuste=col in (4, 15, 18, 19, 20))
        if t.requiere_revision:
            for col in range(1, len(COLUMNAS) + 1):
                p.cell(row=n, column=col).fill = AMBAR
    p.freeze_panes = "E2"
    p.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{max(p.max_row, 2)}"

    _hoja_de_carga(wb, anio, mes)

    pr = wb.create_sheet("Procesos")
    _encabezado(pr, 1, ["Código", "Proceso", "Sigla", "Orden", "Tareas activas", "Tareas desactivadas"], [12, 46, 8, 8, 14, 18])
    for n, x in enumerate(Proceso.objects.order_by("orden"), start=2):
        for col, v in enumerate([x.codigo, x.nombre, x.sigla, x.orden, Tarea.objects.filter(proceso=x, activa=True).count(), Tarea.objects.filter(proceso=x, activa=False).count()], start=1):
            pr.cell(row=n, column=col, value=v)
    pr.freeze_panes = "A2"

    d = wb.create_sheet("Desactivadas")
    _encabezado(d, 1, ["Código", "Proceso", "Tarea principal", "Subtarea", "Responsable que tenía", "Periodicidad", "Cuándo"], [15, 30, 34, 70, 22, 16, 26])
    for n, t in enumerate(Tarea.objects.filter(activa=False).select_related("proceso", "cargo_ejecuta").order_by("codigo"), start=2):
        per, cua = excel_masivo.texto_de_periodicidad(t)
        for col, v in enumerate([t.codigo, t.proceso.nombre, t.tarea_principal, t.subtarea, t.cargo_ejecuta.nombre, per, cua], start=1):
            _poner(d, n, col, v, ajuste=col == 4)
    d.freeze_panes = "A2"

    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def _hoja_de_carga(wb, anio: int, mes: int) -> None:
    """Las horas del mes por persona y día. Si el calendario del mes no está listo, la hoja avisa en vez de fallar."""
    from nucleo.servicios import matriz
    c = wb.create_sheet("Carga por persona y día")
    try:
        m = matriz.construir(anio, mes)
    except Exception:  # calendario sin confirmar o mes sin días hábiles: la hoja lo dice
        c.cell(row=1, column=1, value=f"No se pudo calcular la carga de {mes:02d}-{anio}: confirma los feriados del año en «Abrir mes».")
        return
    c.cell(row=1, column=1, value=f"{mes:02d}-{anio} · horas por persona y día (DH00 a DH10) contra la jornada").font = Font(bold=True, size=13)
    _encabezado(c, 3, ["Cargo", "Concepto"] + [f"DH{i:02d}\n{DIAS[d.weekday()]} {d:%d-%m}" for i, d in enumerate(m.dias)] + ["Total DH00–DH10", "Total del mes", "Tope del mes"], [22, 24] + [11] * len(m.dias) + [16, 14, 12])
    fila = 4
    for f in m.filas:
        c.cell(row=fila, column=1, value=f.cargo.nombre).font = Font(bold=True)
        for k, concepto in enumerate(("Horas planificadas", "Jornada (h)", "Techo de planificación (h)", "% de la jornada")):
            c.cell(row=fila + k, column=2, value=concepto)
        total = 0.0
        for j, d in enumerate(m.dias, start=3):
            horas, cap = f.horas[d], f.capacidad[d]
            total += horas
            techo = cap * m.techo(d)
            celda = c.cell(row=fila, column=j, value=round(horas, 2))
            celda.fill = ROSA if horas > cap + 1e-9 else AMBAR if horas > techo + 1e-9 else VERDE if horas else PatternFill()
            c.cell(row=fila + 1, column=j, value=cap)
            c.cell(row=fila + 2, column=j, value=round(techo, 2))
            c.cell(row=fila + 3, column=j, value=round(horas / cap, 3) if cap else 0).number_format = "0%"
        k = 3 + len(m.dias)
        c.cell(row=fila, column=k, value=round(total, 2))
        c.cell(row=fila, column=k + 1, value=round(f.total_mes, 1))
        c.cell(row=fila, column=k + 2, value=f.tope_mes or "")
        fila += 5
    c.freeze_panes = "C4"
