"""Descarga y carga masiva de Tareas y Procesos en Excel.

- La planilla que se descarga tiene las mismas columnas que el Excel de planificación, así que lo descargado se puede editar y volver a cargar.
- Cargar tareas es en dos pasos: primero una **vista previa** (qué se crea, cambia o se desactiva) y recién después se aplica.
- El archivo se trata como dato, nunca como instrucción: tamaño y filas limitados, fórmulas no se ejecutan (se lee solo el valor) y los textos que
  empiezan con = + - @ se guardan como texto para que Excel no los interprete como fórmula.
- Permisos: Gerente y Jefatura (los mismos que editan tareas); se validan aquí, en el servidor.
"""
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

from nucleo.models import Proceso, Tarea
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


def exportar_tareas() -> bytes:
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "Planificación"
    hoja.cell(row=1, column=1, value=TITULO).font = Font(bold=True, size=13)
    for i, e in enumerate(ENCABEZADOS, start=1):
        c = hoja.cell(row=3, column=i, value=e)
        c.font, c.fill = Font(bold=True), GRIS
    tareas = Tarea.objects.filter(activa=True).select_related("proceso", "cargo_ejecuta", "cargo_revisa", "cargo_cierre", "cargo_revisa_cierre").order_by("proceso__orden", "secuencia", "codigo")
    for n, t in enumerate(tareas, start=4):
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
    for i, linea in enumerate([
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
    ], start=1):
        ayuda.cell(row=i, column=1, value=linea).font = Font(bold=(i == 1))
    ayuda.column_dimensions["A"].width = 150
    return _bytes(wb)


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
