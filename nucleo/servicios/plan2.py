"""Planificación 2.0 (Karla, 03-11-2026): lectura del Excel de tres hojas (Maestro, Diario-Semanal y Mensual) y su carga en la app.

- El plan vigente son las hojas **Diario-Semanal** y **Mensual**; **Maestro** es el respaldo del listado original y no se lee.
- Cada tarea trae su código `OO-PPP.TT.SSS`. La app lo usa como referencia (y para las predecesoras), pero la identidad de la tarea sigue siendo
  proceso + tarea + subtarea. Si el código del archivo mezcla procesos, manda el **nombre del proceso**: la tarea se recodifica al código de su proceso.
- Las fechas del archivo (30-10 al 13-11) son de noviembre de 2026: no se leen; la app las calcula con el calendario de cada mes.

Este módulo no escribe nada: solo lee y propone. Quien escribe es `importador.aplicar`, que llama a `preparar_procesos` y `fijar_predecesoras`.
"""
import difflib
import re
import unicodedata
from collections import Counter


from nucleo import siglas
from nucleo.models import Proceso, Tarea
from nucleo.servicios import importador as imp

HOJAS = ("Diario-Semanal", "Mensual")
PATRON_CODIGO = re.compile(r"^(\d\d)-([A-Z]{3})\.(\d\d)\.(\d{3})$")
MODO_DE_CIERRE = {"pausa": "pausar", "mantiene": "igual", "fuera del equipo contable": "fuera"}
AL_TERMINAR = {"se pone al dia": "al_dia", "se retoma": "retoma"}
DIAS_DE_LA_SEMANA = (("Lun (h)", 0), ("Mar (h)", 1), ("Mié (h)", 2), ("Jue (h)", 3), ("Vie (h)", 4))
FUENTE_DE_HORAS = {"estimada": "estimada", "ajustada": "ajustada"}  # «Original» no cambia lo que ya hay
# Karla (03-11-2026, pregunta 4): las tareas que el archivo trae de 9 minutos (0,15 h: cotejos y descargas con skills) quedan en 10 minutos.
MINUTOS_AJUSTADOS = {9: 10}
# Karla (03-11-2026, pregunta 6): la cuota de contribuciones vence el día 15 de abril, junio, septiembre y noviembre; si cae en día inhábil, se paga el hábil SIGUIENTE (el anterior, en noviembre de 2026, cae en el DH10 y pasa al Contador de su jornada de 5 h).
DIA_DE_VENCIMIENTO = {"13-PBC.03.001": 15}


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def es_plan2(wb) -> bool:
    return all(h in wb.sheetnames for h in HOJAS)


def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hojas_con_tareas(wb):
    for nombre in HOJAS:
        hoja = wb[nombre]
        filas = hoja.iter_rows(values_only=True)
        encabezado = [imp.normalizar(c) for c in next(filas)]
        for n, r in enumerate(filas, start=2):
            if r and r[0] and PATRON_CODIGO.match(imp.normalizar(r[0])):
                yield nombre, n, dict(zip(encabezado, r))


def _cargo(valor) -> str:
    return imp._cargo_de_la_app(imp.normalizar(valor))


def _horas_dh(x: dict, vencimiento: int | None) -> dict | None:
    """Horas por día hábil de la hoja Mensual (columnas DH00…DH10). Solo se guarda si no son todas el día en que vence."""
    d = {str(i): round(_numero(x.get(f"DH{i:02d}")), 4) for i in range(11) if _numero(x.get(f"DH{i:02d}")) is not None}
    if not d or (len(d) == 1 and vencimiento is not None and list(d) == [str(vencimiento)]):
        return None
    return d


def _horas_semana(x: dict, periodicidad: str, horas: float | None) -> dict | None:
    """Horas por día de la semana (hoja Diario-Semanal). Solo se guarda si una diaria no rinde lo mismo todos los días (o no se hace el viernes)."""
    if periodicidad.casefold() != "diaria":
        return None
    d = {str(i): round(_numero(x.get(k)), 4) for k, i in DIAS_DE_LA_SEMANA if _numero(x.get(k)) is not None}
    if not d or (len(d) == 5 and all(abs(v - (horas or 0)) < 1e-6 for v in d.values())):
        return None
    return d


def leer(wb) -> list:
    """Las tareas del plan como `FilaImport` (con `extra` para lo propio de la Planificación 2.0), ordenadas por su código."""
    filas = []
    for hoja, n, x in _hojas_con_tareas(wb):
        codigo = imp.normalizar(x["Código"])
        periodicidad, cuando = imp.normalizar(x.get("Periodicidad")), imp.normalizar(x.get("Cuándo"))
        horas = _numero(x.get("Horas por ejecución"))
        if horas is not None and round(horas * 60) in MINUTOS_AJUSTADOS:
            horas = MINUTOS_AJUSTADOS[round(horas * 60)] / 60
        extra = {"codigo": codigo, "hoja": hoja, "predecesoras": [c.strip() for c in re.split(r"[,;]", imp.normalizar(x.get("Predecesoras"))) if c.strip()],
                 "tipo_control": imp.normalizar(x.get("Tipo de control")), "cambio_plan": imp.normalizar(x.get("Cambio")),
                 "justificacion": imp.normalizar(x.get("Justificación del cambio"))}
        if hoja == "Diario-Semanal":
            modo = imp.normalizar(x.get("Modo en semanas de cierre (DH01–DH10)")).casefold()
            extra["modo_cierre"] = MODO_DE_CIERRE.get(modo, "igual")
            al_terminar = _sin_acentos(imp.normalizar(x.get("Al terminar el cierre")).casefold())
            extra["al_terminar_cierre"] = next((v for k, v in AL_TERMINAR.items() if al_terminar.startswith(k)), "")
            extra["horas_semana"] = _horas_semana(x, periodicidad, horas)
        f = imp.FilaImport(
            fila=n, secuencia=0, proceso=imp.normalizar(x.get("Proceso")), tarea_principal=imp.normalizar(x.get("Tarea principal")),
            subtarea=imp.normalizar(x.get("Subtarea")), ejecuta=_cargo(x.get("Responsable (ejecuta)")), revisa_excel=_cargo(x.get("Revisa")),
            periodicidad=periodicidad, cuando=cuando, fecha_1ra=None, observacion=imp.normalizar(x.get("Observación")), dia_cierre=None,
            horas=horas, ejecuciones=None, fuente_horas=FUENTE_DE_HORAS.get(imp.normalizar(x.get("Fuente de horas")).casefold()),
            modo_cierre=extra.pop("modo_cierre", "igual"), extra=extra,
        )
        if hoja == "Mensual":
            c = imp.convertir_regla(periodicidad, cuando, plan2=True)
            extra["horas_dh"] = _horas_dh(x, c.regla.n if c.regla else None)
        filas.append(f)
    filas.sort(key=lambda f: tuple(PATRON_CODIGO.match(f.extra["codigo"]).group(1, 3, 4)) + (f.extra["codigo"],))
    return filas


def completar_regla(f, conversion):
    """Le pone el día del mes a las reglas por meses a las que el archivo no se lo dice, cuando Karla ya lo definió."""
    from dataclasses import replace
    dia = DIA_DE_VENCIMIENTO.get(f.extra["codigo"]) if f.extra else None
    r = conversion.regla
    if dia and r is not None and r.tipo == "MESES" and r.dia is None:
        return imp.Conversion(replace(r, dia=dia, ajuste="siguiente"), franja=conversion.franja, estado="confirmado", nota=f"Día {dia} definido por Karla (03-11-2026).")
    return conversion


# ---- Procesos: qué número y sigla tiene cada uno -----------------------------------------------------------------------


def resolver_procesos(filas: list) -> dict:
    """{nombre del proceso: (OO, PPP)}. El número y la sigla de un proceso son los del código que más veces lo acompaña. Si dos nombres
    reclaman el mismo código, se queda el que tiene más tareas y el otro es un proceso nuevo con el siguiente número libre."""
    cuentas: dict[str, Counter] = {}
    for f in filas:
        m = PATRON_CODIGO.match(f.extra["codigo"])
        cuentas.setdefault(f.proceso, Counter())[(int(m.group(1)), m.group(2))] += 1
    reclamos = sorted(((c.most_common(1)[0][0], sum(c.values()), nombre) for nombre, c in cuentas.items()), key=lambda t: (-t[1], t[2]))
    resultado, ocupados = {}, set()
    pendientes = []
    for (oo, ppp), _, nombre in reclamos:
        if (oo, ppp) in ocupados or oo in {o for o, _ in ocupados} or ppp in {p for _, p in ocupados}:
            pendientes.append(nombre)
        else:
            resultado[nombre] = (oo, ppp)
            ocupados.add((oo, ppp))
    siguiente = max([o for o, _ in ocupados] + list(Proceso.objects.values_list("orden", flat=True)), default=0) + 1
    usadas = {p for _, p in ocupados} | set(Proceso.objects.values_list("sigla", flat=True))
    for nombre in sorted(pendientes):
        sigla = siglas.derivar(nombre, usadas)
        usadas.add(sigla)
        resultado[nombre] = (siguiente, sigla)
        siguiente += 1
    return resultado


def renombres_de_procesos(procesos: dict) -> dict:
    """{nombre actual: nombre nuevo} para los procesos que ya existen con ese código pero que el plan llama de otra forma."""
    por_codigo = {p.codigo: p for p in Proceso.objects.all()}
    nombres = set(Proceso.objects.values_list("nombre", flat=True))
    renombres = {}
    for nombre, (oo, ppp) in procesos.items():
        actual = por_codigo.get(f"{oo:02d}-{ppp}")
        if actual is not None and actual.nombre != nombre and nombre not in nombres:
            renombres[actual.nombre] = nombre
    return renombres


# ---- Emparejar el plan con las tareas que ya tiene la app ---------------------------------------------------------------


def _txt(texto) -> str:
    return imp.normalizar(texto).casefold()


def emparejar(filas: list, existentes: dict, renombres: dict) -> None:
    """Pone en `f.clave_existente` la clave de la tarea de la app que corresponde a cada fila (o '' si es nueva). En este orden:
    1) misma clave (proceso + tarea + subtarea); 2) misma clave con el proceso ya renombrado; 3) misma tarea y subtarea, aunque haya cambiado de proceso;
    4) mismo proceso y misma subtarea, aunque haya cambiado de tarea; 5) mismo código y subtarea casi igual (se corrigió el texto).
    En los pasos 3 a 5 la pareja debe ser única de los dos lados: si hay duda, la fila es nueva y la antigua se desactiva (tú lo confirmas en la vista previa)."""
    nombre_efectivo = lambda t: renombres.get(t.proceso.nombre, t.proceso.nombre)  # noqa: E731
    efectivas = {imp._clave(nombre_efectivo(t), t.tarea_principal, t.subtarea): t for t in existentes.values()}
    usadas = set()
    for f in filas:
        f.clave_existente = ""
        t = existentes.get(f.clave) or efectivas.get(f.clave)
        if t is not None and t.clave_estable not in usadas:
            f.clave_existente = t.clave_estable
            usadas.add(t.clave_estable)

    def por_llave(llave_fila, llave_tarea):
        libres: dict = {}
        for t in existentes.values():
            if t.clave_estable not in usadas and t.activa:
                libres.setdefault(llave_tarea(t), []).append(t)
        pendientes: dict = {}
        for f in filas:
            if not f.clave_existente:
                pendientes.setdefault(llave_fila(f), []).append(f)
        for llave, fs in pendientes.items():
            if len(fs) == 1 and len(libres.get(llave, [])) == 1:
                t = libres[llave][0]
                fs[0].clave_existente = t.clave_estable
                usadas.add(t.clave_estable)

    por_llave(lambda f: (_txt(f.tarea_principal), _txt(f.subtarea)), lambda t: (_txt(t.tarea_principal), _txt(t.subtarea)))
    por_llave(lambda f: (_txt(f.proceso), _txt(f.subtarea)), lambda t: (_txt(nombre_efectivo(t)), _txt(t.subtarea)))
    por_codigo = {t.codigo: t for t in existentes.values() if t.activa and t.clave_estable not in usadas}
    for f in filas:
        t = por_codigo.get(f.extra["codigo"]) if not f.clave_existente else None
        if t is not None and t.clave_estable not in usadas and difflib.SequenceMatcher(None, _txt(t.subtarea), _txt(f.subtarea)).ratio() >= 0.7:
            f.clave_existente = t.clave_estable
            usadas.add(t.clave_estable)


# ---- Lo que se escribe al aplicar --------------------------------------------------------------------------------------


def preparar_procesos(vp, usuario) -> dict:
    """Antes de las tareas: renombra los procesos que cambiaron de nombre y crea los que faltan con su número y sigla (el «Control del cierre» es el 00).
    Devuelve {nombre: Proceso}."""
    for actual, nuevo in vp.renombres_procesos.items():
        p = Proceso.objects.filter(nombre=actual).first()
        if p is not None:
            p.nombre = nuevo
            p.save()
            for t in Tarea.objects.filter(proceso=p):  # la clave estable cambia con el nombre del proceso
                nueva = imp._clave(p.nombre, t.tarea_principal, t.subtarea)
                if not Tarea.objects.filter(clave_estable=nueva).exclude(pk=t.pk).exists():
                    Tarea.objects.filter(pk=t.pk).update(clave_estable=nueva)
    hechos = {p.nombre: p for p in Proceso.objects.all()}
    for nombre, (oo, ppp) in vp.procesos_plan.items():
        if nombre not in hechos:
            hechos[nombre] = Proceso.objects.create(nombre=nombre, sigla=ppp, orden=oo if not Proceso.objects.filter(orden=oo).exists() else None)
    return hechos


def fijar_predecesoras(vp) -> int:
    """Después de guardar las tareas: las predecesoras del archivo (por código del archivo) pasan a ser vínculos entre tareas."""
    por_codigo = {f.extra["codigo"]: f.clave for f in vp.filas_plan}
    tareas = {t.clave_estable: t for t in Tarea.objects.all()}
    total = 0
    for f in vp.filas_plan:
        t = tareas.get(f.clave)
        if t is None:
            continue
        previas = [tareas[por_codigo[c]] for c in f.extra["predecesoras"] if c in por_codigo and por_codigo[c] in tareas and por_codigo[c] != f.clave]
        t.predecesoras.set(previas)
        total += len(previas)
    return total
