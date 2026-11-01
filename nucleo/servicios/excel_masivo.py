"""Descarga y carga masiva de Tareas y Procesos en Excel.

- La planilla que se descarga tiene las mismas columnas que el Excel de planificación, así que lo descargado se puede editar y volver a cargar.
- Cargar tareas es en dos pasos: primero una **vista previa** (qué se crea, cambia o se desactiva) y recién después se aplica.
- El archivo se trata como dato, nunca como instrucción: tamaño y filas limitados, fórmulas no se ejecutan (se lee solo el valor) y los textos que
  empiezan con = + - @ se guardan como texto para que Excel no los interprete como fórmula.
- Permisos: Gerente y Jefatura (los mismos que editan tareas); se validan aquí, en el servidor.
"""
import copy
import hashlib
import io
import re
import tempfile
import uuid
import zipfile
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException

from django.db import transaction
from django.db.models import Count, Q

from nucleo.models import Cargo, Proceso, Tarea
from nucleo.servicios import auditoria, estructura, importador
from nucleo.servicios.errores import ErrorDeNegocio
from nucleo.servicios.mantenedor import _exigir_edita_tareas
from nucleo.servicios.reglas_texto import MESES, describir
from nucleo.servicios.recurrencia import Regla

MAX_BYTES = 5 * 1024 * 1024
MAX_DESCOMPRIMIDO = 50 * 1024 * 1024
MAX_FILAS = 5000
TITULO = "Hacienda Huentelauquén · Listado maestro de tareas AyF"
ENCABEZADOS = ["Código", "Proceso", "Tarea principal", "Subtarea", "Responsable (ejecuta)", "Revisa", "Periodicidad", "Cuándo", "Observación",
               "Día cierre", "Horas por ejecución", "Ejecuciones por mes", "Semana del cierre", "Responsable en el cierre", "Revisa en el cierre"]
VERDE = PatternFill("solid", start_color=importador.RELLENO_GERENTE, end_color=importador.RELLENO_GERENTE)
GRIS = PatternFill("solid", start_color="FFEDEDED", end_color="FFEDEDED")


# ---- Escribir celdas sin que Excel las lea como fórmula ----------------------------------------------------------


def _poner(hoja, fila: int, columna: int, valor):
    c = hoja.cell(row=fila, column=columna, value=valor)
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@"):
        c.data_type = "s"  # texto, no fórmula
    return c


def _bytes(wb) -> bytes:
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# ---- Tareas: texto de periodicidad ---------------------------------------------------------------------------------


def texto_de_periodicidad(t: Tarea) -> tuple[str, str]:
    """(Periodicidad, Cuándo) tal como los entiende la carga. Si la tarea conserva el texto original del Excel y éste sigue diciendo lo mismo
    que su regla, se devuelve el original; si alguien cambió la regla en el Mantenedor, se escribe de nuevo desde la regla."""
    if t.periodicidad_excel and t.cuando_excel:
        c = importador.convertir_regla(t.periodicidad_excel, t.cuando_excel)
        if c.regla is not None and c.regla == t.regla():
            return t.periodicidad_excel, t.cuando_excel
    r = t.regla()
    if not r.tipo:
        return t.periodicidad_excel, t.cuando_excel
    franja = f" ({t.regla_franja})" if t.regla_franja else ""
    if r.tipo == "DIARIA_HABIL":
        return "Diaria", "Todos los días hábiles"
    if r.tipo == "SEMANAL":
        return "Semanal", (describir(r).replace("Cada ", "").capitalize() if r.dia_semana is not None else "") + (franja if r.dia_semana is not None else "")
    if r.tipo == "CIERRE_DIA_HABIL":
        return "Mensual (cierre)", f"Día hábil {r.n}"
    if r.tipo == "CIERRE_HITO":
        return "Mensual (cierre)", f"D{r.n}"
    if r.tipo == "DIA_FIJO":
        return "Mensual", f"Día {r.dia}"
    if r.tipo == "FIN_DE_MES":
        return "Mensual", "Último día del mes"
    if r.tipo == "MESES":
        meses = ", ".join(MESES[m - 1] for m in r.meses)
        return "Puntual", (f"Día {r.dia} de {meses}" if r.dia else meses.capitalize())
    return "Puntual", "Al ocurrir el evento"


def _revisa(t: Tarea) -> str:
    if t.cargo_revisa is None:
        return ""
    if t.cargo_ejecuta.es_externo and t.cargo_revisa.nombre == importador.CARGO_JEFA and not t.revisa_excel:
        return ""  # es el supuesto de la app, no algo que dijo el Excel
    return t.cargo_revisa.nombre


def _con_plan(t: Tarea, plan, cargos: dict) -> Tarea:
    """Una copia de la tarea (sin guardar) con lo que dice el plan de una propuesta: responsable, día del cierre y semana del cierre."""
    import copy
    c = copy.copy(t)
    c.cargo_ejecuta = cargos.get(plan.ejecuta_id, t.cargo_ejecuta)
    c.regla_tipo, c.regla_n = plan.regla_tipo, plan.regla_n
    c.modo_cierre = plan.modo_cierre
    if plan.minutos is not None:
        c.minutos_estimados = plan.minutos
    c.cargo_cierre = cargos.get(plan.cargo_cierre_id) if plan.cargo_cierre_id else None
    c.cargo_revisa_cierre = cargos.get(plan.revisa_cierre_id) if plan.revisa_cierre_id else None
    if (plan.regla_tipo, plan.regla_n) != (t.regla_tipo, t.regla_n):
        c.periodicidad_excel = c.cuando_excel = ""  # el texto original ya no dice lo mismo: se escribe de nuevo desde la regla
    return c


def exportar_tareas(planes: dict | None = None) -> bytes:
    """La planilla de tareas. Con `planes` (una propuesta de la matriz) escribe lo propuesto en vez de lo vigente."""
    cargos = {c.pk: c for c in Cargo.objects.all()} if planes else {}
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "Planificación"
    hoja.cell(row=1, column=1, value=TITULO).font = Font(bold=True, size=13)
    for i, e in enumerate(ENCABEZADOS, start=1):
        c = hoja.cell(row=3, column=i, value=e)
        c.font, c.fill = Font(bold=True), GRIS
    tareas = Tarea.objects.filter(activa=True).select_related("proceso", "cargo_ejecuta", "cargo_revisa", "cargo_cierre", "cargo_revisa_cierre").order_by("proceso__orden", "secuencia", "codigo")
    for n, t in enumerate(tareas, start=4):
        if planes and t.pk in planes:
            t = _con_plan(t, planes[t.pk], cargos)
        per, cua = texto_de_periodicidad(t)
        valores = [t.codigo, t.proceso.nombre, t.tarea_principal, t.subtarea, t.cargo_ejecuta.nombre, _revisa(t), per, cua, t.referencia_normativa, t.dia_cierre,
                   None if t.minutos_estimados is None else round(t.minutos_estimados / 60, 4), None if t.ejecuciones_mes is None else float(t.ejecuciones_mes),
                   {"igual": "", "reasignar": "Reasignar", "pausar": "Pausar"}[t.modo_cierre], t.cargo_cierre.nombre if t.cargo_cierre else "", t.cargo_revisa_cierre.nombre if t.cargo_revisa_cierre else ""]
        for col, v in enumerate(valores, start=1):
            _poner(hoja, n, col, v)
        if t.fuente_horas == "gerente":
            hoja.cell(row=n, column=11).fill = VERDE
    for col, ancho in zip("ABCDEFGHIJKLMNO", (24, 28, 34, 54, 22, 18, 18, 26, 30, 11, 12, 12, 14, 22, 22)):
        hoja.column_dimensions[col].width = ancho
    hoja.freeze_panes = "C4"
    ayuda = wb.create_sheet("Instrucciones")
    for i, linea in enumerate(INSTRUCCIONES, start=1):
        ayuda.cell(row=i, column=1, value=linea).font = Font(bold=(i == 1))
    ayuda.column_dimensions["A"].width = 150
    return _bytes(wb)


INSTRUCCIONES = [
    "Cómo usar esta planilla",
    "1. Edita lo que necesites. Cada fila es una subtarea; las filas van en el orden en que se procesan.",
    "2. La columna «Código» solo sirve para ubicarte: la app no la lee. Una tarea es la misma mientras no cambies Proceso + Tarea principal + Subtarea.",
    "3. Si cambias el texto de Proceso, Tarea principal o Subtarea, la app lo toma como una tarea nueva y desactiva la anterior (te lo avisa en la vista previa).",
    "4. Responsable y Revisa deben ser nombres de cargo que ya existen (por ejemplo «Contador Senior»). «Revisa» puede ir vacío.",
    "5. Periodicidad y Cuándo: Diaria · Todos los días hábiles / Semanal · Lunes / Mensual (cierre) · Día hábil 3 (del 1 al 7) / Mensual (cierre) · D8, D9 o D10 (días del mes: "
    "reportes listos en la tarde, Gerente General y Directorio; si caen en día inhábil pasan al hábil siguiente) / Mensual · Día 13 / Mensual · Último día del mes / "
    "Puntual · Día 20 de abril, junio y septiembre.",
    "5b. Semana del cierre (del primer día hábil al día 8): vacío = la tarea sigue igual · «Pausar» = no se hace esa semana · «Reasignar» = la hace «Responsable en el cierre» "
    "y la revisa «Revisa en el cierre» (si queda vacío, el revisor de siempre).",
    "6. El ajuste «día hábil siguiente» de un día fijo no se puede escribir aquí: se cambia en Mantenedor → Tareas.",
    "7. Las tareas que no estén en el archivo se DESACTIVAN (no se borran). La app te muestra la lista antes de aplicar y pide confirmación.",
    "8. Celda de horas en verde = horas definidas por la Gerente AyF.",
]


# ---- La matriz del cierre (para que Karla la revise antes de entregarla) -------------------------------------------------------------

ROJO = PatternFill("solid", start_color="FFF8D7DA", end_color="FFF8D7DA")
AMBAR = PatternFill("solid", start_color="FFFFF3CD", end_color="FFFFF3CD")
OK = PatternFill("solid", start_color="FFD1E7DD", end_color="FFD1E7DD")
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _relleno(horas: float, capacidad: float):
    if horas > capacidad + 1e-9:
        return ROJO
    return AMBAR if capacidad and horas >= capacidad * 0.9 else (OK if horas else None)


def _hoja_de_matriz(wb, titulo: str, m) -> None:
    hoja = wb.create_sheet(titulo)
    hoja.cell(row=1, column=1, value=f"{titulo} · horas por persona y día · {m.mes:02d}-{m.anio}").font = Font(bold=True, size=13)
    hoja.cell(row=2, column=1, value="Rojo: supera la jornada del día (lunes a jueves 9 h, viernes 5 h) · Ámbar: desde el 90 % · Verde: dentro de la jornada. Horas ESTIMADAS.")
    encabezados = ["Cargo"] + [f"{DIAS_CORTOS[f.weekday()]} {f:%d-%m}" + (f"\n{m.etiqueta(f)}" if m.etiqueta(f) else "") for f in m.dias] + ["Hasta el día 8", "Capacidad hasta el día 8", "Ocupación", "Total del mes", "Tope del mes"]
    for i, e in enumerate(encabezados, start=1):
        c = hoja.cell(row=4, column=i, value=e)
        c.font, c.fill, c.alignment = Font(bold=True), GRIS, Alignment(wrap_text=True, vertical="top", horizontal="center")
    n = 5
    for fila in m.filas:
        hoja.cell(row=n, column=1, value=fila.cargo.nombre).font = Font(bold=True)
        for col, f in enumerate(m.dias, start=2):
            c = hoja.cell(row=n, column=col, value=round(fila.horas[f], 2))
            relleno = _relleno(fila.horas[f], fila.capacidad[f])
            if relleno:
                c.fill = relleno
            c.number_format = "0.0"
        k = len(m.dias) + 2
        for extra, v in enumerate([round(fila.horas_semana_cierre, 1), round(fila.capacidad_semana_cierre, 1), f"{fila.ocupacion_pct}%", round(fila.total_mes, 1), fila.tope_mes or ""]):
            c = hoja.cell(row=n, column=k + extra, value=v)
            if extra == 4 and fila.pasa_el_tope:
                c.fill = ROJO
        n += 1
    hoja.cell(row=n, column=1, value="Jornada del día").font = Font(italic=True)
    for col, f in enumerate(m.dias, start=2):
        hoja.cell(row=n, column=col, value=m.filas[0].capacidad[f] if m.filas else 0).font = Font(italic=True)
    hoja.column_dimensions["A"].width = 22
    for col in range(2, len(encabezados) + 1):
        hoja.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 14
    hoja.row_dimensions[4].height = 48
    hoja.freeze_panes = "B5"


def exportar_matriz(anio: int, mes: int) -> bytes:
    """Matriz del cierre de un mes: como está hoy y como quedaría con la propuesta, con el detalle día por día, los cambios y la planilla de tareas con la propuesta aplicada."""
    from nucleo.servicios import matriz
    prop = matriz.proponer(anio, mes)
    antes, despues = prop.antes, prop.despues
    wb = openpyxl.Workbook()
    r = wb.active
    r.title = "Resumen"
    r["A1"] = f"Matriz del cierre · {mes:02d}-{anio}"
    r["A1"].font = Font(bold=True, size=14)
    lineas = [
        "Para revisar antes de entregarla. Todo son horas ESTIMADAS (la mayoría, estimación base de Legión; 24 definidas por la Gerente AyF): si una hora está mal, corrígela en la planilla de tareas.",
        "Jornada: lunes a jueves 9 h y viernes 5 h (41 h a la semana). Gerente AyF: máximo 80 h al mes para Huentelauquén.",
        "Semana del cierre: del primer día hábil al día 8 (reportes listos en la tarde). Día 9: Gerente General. Día 10: Directorio. Si caen en día inhábil, pasan al hábil siguiente.",
        "Regla de operación propuesta: la Asistente Contable cubre compras y pagos (el Contador Senior solo revisa); Jefa de Control, Contador Senior y Gerente AyF se enfocan 100 % en el cierre.",
    ]
    for i, linea in enumerate(lineas, start=3):
        r.cell(row=i, column=1, value=linea)
    fila0 = len(lineas) + 5
    for i, e in enumerate(["Cargo", "Horas hasta el día 8 · hoy", "Horas hasta el día 8 · propuesta", "Capacidad hasta el día 8", "Ocupación · hoy", "Ocupación · propuesta", "Total del mes · propuesta", "Tope del mes"], start=1):
        c = r.cell(row=fila0, column=i, value=e)
        c.font, c.fill, c.alignment = Font(bold=True), GRIS, Alignment(wrap_text=True, vertical="top")
    for k, (a, d) in enumerate(zip(antes.filas, despues.filas), start=fila0 + 1):
        for col, v in enumerate([a.cargo.nombre, round(a.horas_semana_cierre, 1), round(d.horas_semana_cierre, 1), round(d.capacidad_semana_cierre, 1), f"{a.ocupacion_pct}%", f"{d.ocupacion_pct}%", round(d.total_mes, 1), d.tope_mes or ""], start=1):
            c = r.cell(row=k, column=col, value=v)
            if col == 6 and d.ocupacion_pct > 100:
                c.fill = ROJO
    k = fila0 + len(antes.filas) + 1
    for col, v in enumerate(["Equipo", round(antes.horas_semana_cierre, 1), round(despues.horas_semana_cierre, 1), round(despues.capacidad_semana_cierre, 1),
                             f"{round(antes.horas_semana_cierre * 100 / antes.capacidad_semana_cierre)}%" if antes.capacidad_semana_cierre else "", f"{round(despues.horas_semana_cierre * 100 / despues.capacidad_semana_cierre)}%" if despues.capacidad_semana_cierre else ""], start=1):
        r.cell(row=k, column=col, value=v).font = Font(bold=True)
    veredicto = ("Con estas horas estimadas el trabajo hasta el día 8 SUPERA lo que el equipo puede hacer en su jornada: faltan "
                 f"{max(0.0, round(despues.horas_semana_cierre - despues.capacidad_semana_cierre, 1))} h. Hay que bajar horas, mover tareas más allá del día 8 o sumar apoyo.") \
        if despues.horas_semana_cierre > despues.capacidad_semana_cierre + 1e-9 else "Con estas horas el trabajo hasta el día 8 cabe en la jornada del equipo."
    r.cell(row=k + 2, column=1, value=veredicto).font = Font(bold=True)
    for extra, linea in enumerate(matriz.diagnostico(prop), start=5):
        r.cell(row=k + extra, column=1, value=("Diagnóstico · " if extra == 5 else "") + linea)
    r.cell(row=k + 3, column=1, value=f"Desequilibrio entre el cargo más y el menos ocupado: hoy {antes.desequilibrio_pct} puntos · propuesta {despues.desequilibrio_pct} puntos. Horas de más sobre la jornada (suma de los días con exceso): hoy {round(antes.exceso_total, 1)} h · propuesta {round(despues.exceso_total, 1)} h.")
    r.column_dimensions["A"].width = 26
    for col in "BCDEFGH":
        r.column_dimensions[col].width = 20
    _hoja_de_matriz(wb, "Matriz hoy", antes)
    _hoja_de_matriz(wb, "Matriz propuesta", despues)

    d = wb.create_sheet("Detalle por día")
    for i, e in enumerate(["Escenario", "Fecha", "Cargo", "Código", "Proceso", "Tarea", "Tipo", "Horas"], start=1):
        c = d.cell(row=1, column=i, value=e)
        c.font, c.fill = Font(bold=True), GRIS
    n = 2
    for nombre, m in (("Hoy", antes), ("Propuesta", despues)):
        for fila in m.filas:
            for f in m.dias:
                for it in fila.items[f]:
                    for col, v in enumerate([nombre, f, fila.cargo.nombre, it.codigo, it.proceso, it.texto, it.tipo, round(it.horas, 2)], start=1):
                        c = _poner(d, n, col, v)
                        if col == 2:
                            c.number_format = "dd-mm-yyyy"
                    n += 1
    for col, ancho in zip("ABCDEFGH", (11, 12, 20, 16, 28, 70, 10, 8)):
        d.column_dimensions[col].width = ancho
    d.auto_filter.ref = d.dimensions
    d.freeze_panes = "A2"

    c = wb.create_sheet("Cambios propuestos")
    for i, e in enumerate(["Código", "Proceso", "Tarea", "Qué cambia", "Antes", "Después", "Por qué"], start=1):
        cel = c.cell(row=1, column=i, value=e)
        cel.font, cel.fill = Font(bold=True), GRIS
    for n, cambio in enumerate(prop.cambios, start=2):
        for col, v in enumerate([cambio.tarea.codigo, cambio.tarea.proceso.nombre, cambio.tarea.subtarea, cambio.campo, cambio.antes, cambio.despues, cambio.motivo], start=1):
            _poner(c, n, col, v)
    for col, ancho in zip("ABCDEFG", (16, 26, 60, 22, 24, 40, 70)):
        c.column_dimensions[col].width = ancho
    c.auto_filter.ref = c.dimensions
    c.freeze_panes = "A2"

    a = wb.create_sheet("Alertas")
    a["A1"] = "Lo que sigue sin caber después de la propuesta"
    a["A1"].font = Font(bold=True)
    alertas = despues.alertas() or ["Nada: con la propuesta todos caben en su jornada."]
    for n, texto in enumerate(alertas, start=3):
        a.cell(row=n, column=1, value=texto)
    a.column_dimensions["A"].width = 130

    p = wb.create_sheet("Planificación")
    _volcar_planilla(p, prop.planes)
    ayuda = wb.create_sheet("Instrucciones")
    for i, linea in enumerate([
        "Cómo usar este libro",
        "1. Revisa «Resumen», «Matriz hoy» y «Matriz propuesta» (rojo = más horas que la jornada). «Detalle por día» lista cada tarea; «Cambios propuestos» dice qué se movió y por qué.",
        "2. La hoja «Planificación» es la planilla de tareas CON LA PROPUESTA YA APLICADA (responsables, día del cierre y semana del cierre). No se aplica sola.",
        "3. Si estás de acuerdo (o después de corregirla a mano), en la app: Mantenedor → Tareas → Cargar Excel y sube este mismo archivo. La app te muestra primero qué cambiaría.",
        "4. La propuesta está calculada con el calendario de este mes; en otros meses los días 8, 9 y 10 caen en otras fechas.",
    ], start=1):
        ayuda.cell(row=i, column=1, value=linea).font = Font(bold=(i == 1))
    ayuda.column_dimensions["A"].width = 150
    return _bytes(wb)


def _volcar_planilla(hoja, planes: dict) -> None:
    """Escribe la planilla de tareas (con una propuesta aplicada) en una hoja ya creada."""
    libro = openpyxl.load_workbook(io.BytesIO(exportar_tareas(planes)))
    origen = libro["Planificación"]
    for fila in origen.iter_rows():
        for c in fila:
            if c.value is not None:
                n = hoja.cell(row=c.row, column=c.column, value=c.value)
                if isinstance(c.value, str) and c.value[:1] in ("=", "+", "-", "@"):
                    n.data_type = "s"
                if c.has_style:
                    n.font, n.fill = copy.copy(c.font), copy.copy(c.fill)
    for col, dim in origen.column_dimensions.items():
        hoja.column_dimensions[col].width = dim.width
    hoja.freeze_panes = "C4"


# ---- La planificación completa (solo lectura: no se vuelve a cargar) ---------------------------------------------------------


def exportar_planificacion(filas) -> bytes:
    """La estructura de tres niveles, tal como se ve en pantalla (con los filtros aplicados). Para leer y compartir; para editar en masa se usa la planilla de tareas."""
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "Planificación"
    encabezados = ["Nivel", "Código", "Orden del proceso", "Proceso", "Tarea", "Subtarea", "Responsable", "Estado", "Fecha de inicio", "Fecha de término", "Observaciones", "Activo", "Depende de"]
    for i, e in enumerate(encabezados, start=1):
        c = hoja.cell(row=1, column=i, value=e)
        c.font, c.fill = Font(bold=True), GRIS
    for n, f in enumerate(filas, start=2):
        valores = [{1: "Proceso", 2: "Tarea", 3: "Subtarea"}[f.nivel], f.codigo, f.orden, f.proceso, f.tarea, f.subtarea, f.responsable, f.estado, f.fecha_inicio, f.fecha_termino,
                   f.observaciones, "Sí" if f.activo else "No", f.depende_de]
        for col, v in enumerate(valores, start=1):
            c = _poner(hoja, n, col, v)
            if f.nivel == 1:
                c.font = Font(bold=True)
            if hasattr(v, "year"):
                c.number_format = "dd-mm-yyyy"
    for col, ancho in zip("ABCDEFGHIJKLM", (10, 18, 10, 34, 34, 54, 22, 13, 13, 13, 30, 8, 20)):
        hoja.column_dimensions[col].width = ancho
    hoja.freeze_panes = "C2"
    hoja.auto_filter.ref = hoja.dimensions
    return _bytes(wb)


# ---- Procesos ---------------------------------------------------------------------------------------------------


def exportar_procesos() -> bytes:
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "Procesos"
    for i, e in enumerate(["Orden", "Código", "Sigla", "Proceso", "Tareas activas", "Activo"], start=1):
        c = hoja.cell(row=1, column=i, value=e)
        c.font, c.fill = Font(bold=True), GRIS
    procesos = Proceso.objects.annotate(n=Count("tareas", filter=Q(tareas__activa=True))).order_by("orden", "nombre")
    for n, p in enumerate(procesos, start=2):
        for col, v in enumerate([p.orden, p.codigo, p.sigla, p.nombre, p.n, "Sí" if p.activo else "No"], start=1):
            _poner(hoja, n, col, v)
    for col, ancho in zip("ABCDEF", (8, 12, 8, 44, 14, 8)):
        hoja.column_dimensions[col].width = ancho
    hoja.cell(row=len(procesos) + 4, column=1, value="Para reordenar cambia la columna «Orden» (o mueve las filas) y vuelve a cargar. «Activo»: Sí o No. "
              "Un proceso nuevo se agrega con su nombre (y su sigla de 3 letras, si no la propone la app). El «Código» lo genera la app: al cambiar el orden o la sigla se actualiza solo. "
              "Los procesos que no estén en el archivo quedan como están, después de los demás.")
    return _bytes(wb)


def _si_no(valor, por_defecto: bool = True) -> bool:
    v = importador._sin_acentos(importador.normalizar(valor).casefold())
    if v in ("si", "s", "1", "true", "activo", "x"):
        return True
    if v in ("no", "n", "0", "false", "inactivo"):
        return False
    return por_defecto


# ---- Validar el archivo ----------------------------------------------------------------------------------------------


def validar_archivo(contenido: bytes, nombre: str = ""):
    if nombre and not nombre.lower().endswith(".xlsx"):
        raise ErrorDeNegocio("El archivo debe ser un Excel .xlsx.")
    if not contenido:
        raise ErrorDeNegocio("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ErrorDeNegocio("El archivo pesa más de 5 MB: revisa que sea la planilla correcta.")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPRIMIDO:
                raise ErrorDeNegocio("El archivo es demasiado grande al abrirlo.")
    except zipfile.BadZipFile:
        raise ErrorDeNegocio("No se pudo abrir el archivo: no parece un Excel .xlsx válido.") from None


def _abrir(contenido: bytes):
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise ErrorDeNegocio("No se pudo abrir el archivo: no parece un Excel .xlsx válido.") from None
    if any(h.max_row > MAX_FILAS for h in wb.worksheets):
        raise ErrorDeNegocio(f"El archivo tiene más de {MAX_FILAS} filas: revisa que sea la planilla correcta.")
    return wb


# ---- Cargar procesos -----------------------------------------------------------------------------------------------


@transaction.atomic
def cargar_procesos(usuario, contenido: bytes, nombre_archivo: str = "") -> dict:
    """Ordena, activa/desactiva y agrega procesos desde un Excel. No renombra: un proceso se reconoce por su nombre."""
    _exigir_edita_tareas(usuario)
    validar_archivo(contenido, nombre_archivo)
    wb = _abrir(contenido)
    hoja = wb["Procesos"] if "Procesos" in wb.sheetnames else wb.worksheets[0]
    filas = list(hoja.iter_rows(values_only=True))
    inicio = next((i for i, r in enumerate(filas) if r and any(importador.normalizar(c).casefold() == "proceso" for c in r)), None)
    if inicio is None:
        raise ErrorDeNegocio("El Excel no tiene la columna «Proceso».")
    cols = {importador.normalizar(c).casefold(): i for i, c in enumerate(filas[inicio]) if c}
    i_nombre, i_orden, i_activo, i_sigla = cols["proceso"], cols.get("orden"), cols.get("activo"), cols.get("sigla")
    pedidos, vistos = [], set()
    for n, r in enumerate(filas[inicio + 1:], start=1):
        nombre = importador.normalizar(r[i_nombre]) if i_nombre < len(r) else ""
        if not nombre or nombre.casefold() in vistos or not any(isinstance(c, (str, int, float)) for c in r[:1] + r[i_nombre:i_nombre + 1]):
            continue
        if i_orden is None and nombre.startswith("Para reordenar"):
            continue
        vistos.add(nombre.casefold())
        orden = r[i_orden] if i_orden is not None and i_orden < len(r) else None
        orden = float(orden) if isinstance(orden, (int, float)) and not isinstance(orden, bool) else float(n)
        activo = _si_no(r[i_activo]) if i_activo is not None and i_activo < len(r) else None
        sigla = importador.normalizar(r[i_sigla]).upper() if i_sigla is not None and i_sigla < len(r) else ""
        pedidos.append((orden, n, nombre, activo, sigla))
    if not pedidos:
        raise ErrorDeNegocio("El Excel no trae procesos.")
    existentes = {p.nombre.casefold(): p for p in Proceso.objects.all()}
    creados = reordenados = cambios_activo = 0
    en_archivo = []
    for orden, _, nombre, activo, sigla in sorted(pedidos):
        p = existentes.get(nombre.casefold())
        if p is None:
            if Proceso.objects.count() >= estructura.MAX_PROCESOS:
                raise ErrorDeNegocio(f"Se admiten hasta {estructura.MAX_PROCESOS} procesos.")
            p = Proceso(nombre=nombre, activo=True if activo is None else activo, sigla=estructura.validar_sigla(sigla) if sigla else "")  # el orden definitivo se asigna abajo
            p.save()
            creados += 1
        else:
            if sigla and sigla != p.sigla:
                p.sigla = estructura.validar_sigla(sigla, excepto=p)  # cambia el código de todo el proceso, con historial
                p.save()
            if activo is not None and activo != p.activo:
                estructura.fijar_activo_proceso(usuario, p, activo)
                cambios_activo += 1
        en_archivo.append(p.pk)
    resto = [p.pk for p in Proceso.objects.exclude(pk__in=en_archivo).order_by("orden", "nombre")]
    antes = dict(Proceso.objects.values_list("pk", "orden"))
    estructura.reordenar_procesos(usuario, en_archivo + resto, motivo="Orden de la carga desde Excel", validar_permiso=False)
    reordenados = sum(1 for pk, orden in Proceso.objects.values_list("pk", "orden") if antes.get(pk) != orden)
    resumen = {"creados": creados, "reordenados": reordenados, "activo_cambiado": cambios_activo, "en_archivo": len(en_archivo)}
    auditoria.registrar("procesos.cargados", usuario=usuario, entidad="Proceso", despues={**resumen, "archivo": nombre_archivo, "sha256": hashlib.sha256(contenido).hexdigest()})
    return resumen


# ---- Cargar tareas (vista previa y aplicar) ------------------------------------------------------------------------


class Problema(ErrorDeNegocio):
    """Lo que impide aplicar el archivo; el texto lista todas las filas con problema."""


def previsualizar_tareas(usuario, contenido: bytes, nombre_archivo: str = ""):
    _exigir_edita_tareas(usuario)
    validar_archivo(contenido, nombre_archivo)
    _abrir(contenido)  # valida filas y formato antes de leer
    try:
        vp = importador.previsualizar(io.BytesIO(contenido), incluir_dia_9=False)
    except KeyError as e:
        raise ErrorDeNegocio(f"{e.args[0]}") from None
    except StopIteration:
        raise ErrorDeNegocio("El Excel no tiene la fila de encabezados (Proceso, Tarea principal, Subtarea…).") from None
    if not vp.total_filas:
        raise ErrorDeNegocio("El Excel no trae tareas.")
    return vp


def problemas_para_aplicar(vp) -> list[str]:
    """Cosas que no se deben dejar pasar en una carga masiva: filas sin responsable o con cargos que no existen (suele ser un error de tipeo)."""
    problemas = []
    for f in list(vp.altas) + [f for _, f, _ in vp.cambios]:
        if not f.ejecuta:
            problemas.append(f"Fila {f.fila}: falta el responsable (ejecuta).")
    for f in list(vp.altas) + [f for _, f, _ in vp.cambios]:
        if f.modo_cierre == "reasignar" and not f.cargo_cierre:
            problemas.append(f"Fila {f.fila}: «Reasignar» necesita el responsable en el cierre.")
        if f.cargo_cierre and f.cargo_cierre == f.ejecuta and f.modo_cierre == "reasignar":
            problemas.append(f"Fila {f.fila}: el responsable en el cierre es el mismo de siempre; usa «Pausar» o déjala igual.")
    conocidos = set(importador.ORDEN_CARGOS) | importador.CARGOS_EXTERNOS
    for nombre in vp.cargos_nuevos:
        if nombre not in conocidos:
            problemas.append(f"El cargo «{nombre}» no existe. Revisa que esté bien escrito (por ejemplo «Contador Senior»).")
    return problemas


def aplicar_tareas(usuario, contenido: bytes, nombre_archivo: str = "", confirma_desactivar: bool = False) -> dict:
    vp = previsualizar_tareas(usuario, contenido, nombre_archivo)
    problemas = problemas_para_aplicar(vp)
    if problemas:
        raise Problema(" ".join(problemas[:6]) + (f" (y {len(problemas) - 6} más)" if len(problemas) > 6 else ""))
    if vp.bajas and not confirma_desactivar:
        raise ErrorDeNegocio(f"Esta carga desactiva {len(vp.bajas)} tarea(s) que no están en el archivo. Marca la confirmación para continuar.")
    with transaction.atomic():
        return importador.aplicar(vp, usuario, detalle={"origen": "carga masiva", "archivo": nombre_archivo, "sha256": hashlib.sha256(contenido).hexdigest()})


# ---- Archivo en espera entre la vista previa y la confirmación --------------------------------------------------------

_TOKEN = re.compile(r"^[0-9a-f]{32}$")


def _carpeta() -> Path:
    c = Path(tempfile.gettempdir()) / "planificacion_cargas"
    c.mkdir(mode=0o700, exist_ok=True)
    return c


def guardar_en_espera(contenido: bytes) -> str:
    token = uuid.uuid4().hex
    (_carpeta() / f"{token}.xlsx").write_bytes(contenido)
    return token


def leer_en_espera(token: str) -> bytes:
    if not _TOKEN.match(token or ""):
        raise ErrorDeNegocio("La carga venció. Sube el archivo de nuevo.")
    ruta = _carpeta() / f"{token}.xlsx"
    if not ruta.is_file():
        raise ErrorDeNegocio("La carga venció. Sube el archivo de nuevo.")
    return ruta.read_bytes()


def borrar_en_espera(token: str):
    if _TOKEN.match(token or ""):
        (_carpeta() / f"{token}.xlsx").unlink(missing_ok=True)


def nombre_de_descarga(prefijo: str, hoy: date) -> str:
    return f"{prefijo}_{hoy:%Y%m%d}.xlsx"
