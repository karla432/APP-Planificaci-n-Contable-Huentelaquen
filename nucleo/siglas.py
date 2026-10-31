"""Siglas de proceso (PPP): tres letras mayúsculas, únicas, que identifican al proceso en el código OO-PPP.TT.SSS.

Sin dependencias de Django para poder usarlas también en migraciones.
"""
import re
import unicodedata

PATRON = re.compile(r"^[A-Z]{3}$")
PALABRAS_VACIAS = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "E", "POR", "EN", "A", "AL"}

# Procesos de la planificación de Hacienda Huentelauquén (Excel del 31-10-2026). Propuesta editable desde el Mantenedor.
# Donde un proceso equivale a uno del catálogo base (VEN, COM, TES, ACT, CON) se usa la misma sigla.
SIGLAS_HACIENDA = {
    "Seguimiento": "SEG", "Ventas Sala de Ventas": "VEN", "Ventas Santiago": "VST", "Ventas Hacienda": "VHA", "Ventas Consolidada": "VCO",
    "Reporte Semanal": "RSE", "Cobranza": "COB", "Compras": "COM", "Fondos por rendir": "FPR", "Honorarios": "HON", "Cierre Honorarios": "CHO",
    "Pagos Banco Estado": "PBE", "Pagos Banco de Chile": "PBC", "Bancos": "BAN", "Tesorería": "TES", "Producción": "PRO", "Cierre Compras": "CCO",
    "Cierre Ventas": "CVE", "Conciliación Transbank": "CTR", "Conciliación bancaria": "CBA", "Remuneraciones": "REM", "Activos fijos": "ACT",
    "Créditos y leasing": "CYL", "Inversiones": "IVS", "Gastos diferidos y corrección monetaria": "GDC", "Provisiones": "PRV", "Contabilidad": "CON",
    "Producción e inventario": "PEI", "Activación": "ACV", "Costeo y producción": "CYP", "Análisis de cuentas": "ACU", "F29": "FOR",
    "Reportería día 7": "RPT", "Revisión día 9": "RGG", "Cierre día 10": "CDF",
}

# Catálogo base (instalaciones nuevas): sigla, nombre y de quién depende. El orden es el de la lista y es editable.
CATALOGO_BASE = [
    ("PLA", "Planificación y configuración contable", []),
    ("VEN", "Ventas y sala de venta", ["PLA"]),
    ("CXC", "Cuentas por cobrar", ["VEN"]),
    ("COM", "Compras", ["PLA"]),
    ("CXP", "Cuentas por pagar", ["COM"]),
    ("TES", "Tesorería y bancos", ["CXC", "CXP"]),
    ("INV", "Inventario y valorización", ["VEN", "COM"]),
    ("ACT", "Activo fijo", ["COM"]),
    ("CON", "Contabilidad general", ["TES", "INV", "ACT"]),
    ("IMP", "Impuestos", ["CON"]),
    ("CIE", "Cierre contable", ["CON", "IMP"]),
]


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def valida(sigla: str) -> bool:
    return bool(PATRON.match(sigla or ""))


def derivar(nombre: str, ocupadas: set[str]) -> str:
    """Una sigla libre a partir del nombre: iniciales si hay 3 o más palabras; si no, las 3 primeras letras. Si está ocupada, varía la última letra."""
    palabras = [p for p in re.findall(r"[A-Z]+", sin_acentos(nombre).upper()) if p not in PALABRAS_VACIAS] or ["XXX"]
    if len(palabras) >= 3:
        base = "".join(p[0] for p in palabras[:3])
    else:
        base = "".join(palabras)[:3].ljust(3, "X")
    if base not in ocupadas:
        return base
    for posicion in (2, 1, 0):
        for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidata = base[:posicion] + letra + base[posicion + 1:]
            if candidata not in ocupadas:
                return candidata
    raise ValueError("No quedan siglas libres para ese nombre.")
