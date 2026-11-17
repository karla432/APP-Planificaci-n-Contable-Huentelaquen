"""Segundo factor de ingreso (TOTP, RFC 6238), obligatorio para el Gerente AyF y el administrador del sistema (docs/f1/03_kpi_roles_sod.md).

- El código son 6 dígitos que cambian cada 30 segundos en la aplicación de la persona (Google Authenticator, Microsoft Authenticator, etc.).
- Un código ya usado no sirve otra vez; cinco códigos errados seguidos bloquean 15 minutos (el mismo bloqueo del ingreso).
- Todo queda en la bitácora. En producción no se puede apagar (`settings.EXIGE_2FA`).
"""
import hmac
import time

import pyotp
from django.conf import settings

from nucleo import bloqueo_acceso, permisos
from nucleo.models import SegundoFactor
from nucleo.servicios import auditoria
from nucleo.servicios.errores import ErrorDeNegocio

ROLES_QUE_LO_EXIGEN = (permisos.GERENTE, permisos.ADMIN_SISTEMA)
EMISOR = "Planificación Contable Huentelauquén"
CLAVE_DE_SESION = "segundo_factor_ok"
PASO = 30


def exige(usuario) -> bool:
    return bool(settings.EXIGE_2FA) and permisos.rol_de(usuario) in ROLES_QUE_LO_EXIGEN


def de(usuario) -> SegundoFactor | None:
    return SegundoFactor.objects.filter(usuario=usuario).first()


def crear(usuario, visible_en_pantalla: bool = False) -> SegundoFactor:
    """Crea (o deja la que ya existe) la clave de la persona. Con `visible_en_pantalla` la pantalla de alta la muestra hasta que se confirme."""
    sf, creado = SegundoFactor.objects.get_or_create(usuario=usuario, defaults={"secreto": pyotp.random_base32(), "visible_en_pantalla": visible_en_pantalla})
    if creado:
        auditoria.registrar("2fa.creado", usuario=usuario, entidad="Usuario", entidad_id=usuario.pk)
    return sf


def reiniciar(usuario) -> None:
    """Borra el segundo factor para que la persona vuelva a darlo de alta (cambio de teléfono). Lo hace el administrador desde la consola."""
    SegundoFactor.objects.filter(usuario=usuario).delete()
    bloqueo_acceso.limpiar(f"2fa:{usuario.username}")
    auditoria.registrar("2fa.reiniciado", usuario=None, entidad="Usuario", entidad_id=usuario.pk, motivo=f"Cuenta {usuario.username}")


def uri(sf: SegundoFactor) -> str:
    return pyotp.TOTP(sf.secreto).provisioning_uri(name=sf.usuario.username, issuer_name=EMISOR)


def clave_legible(sf: SegundoFactor) -> str:
    return " ".join(sf.secreto[i:i + 4] for i in range(0, len(sf.secreto), 4))


def qr_svg(sf: SegundoFactor) -> str:
    """El código QR como SVG, si el servidor tiene instalada la librería `qrcode`; si no, vacío (se escribe la clave a mano)."""
    try:
        import io

        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    salida = io.BytesIO()
    qrcode.make(uri(sf), image_factory=qrcode.image.svg.SvgPathImage).save(salida)
    return salida.getvalue().decode("utf-8")


def minutos_de_bloqueo(usuario) -> int:
    return bloqueo_acceso.minutos_restantes(f"2fa:{usuario.username}")


def verificar(usuario, codigo, ahora: float | None = None) -> bool:
    """True si el código es válido ahora (con 30 segundos de tolerancia a cada lado) y no se había usado. Cuenta los fallos."""
    nombre = f"2fa:{usuario.username}"
    if bloqueo_acceso.esta_bloqueado(nombre):
        raise ErrorDeNegocio(f"Demasiados códigos errados. Vuelve a intentar en {minutos_de_bloqueo(usuario)} minuto(s).")
    sf = de(usuario)
    codigo = "".join(c for c in str(codigo or "") if c.isdigit())
    if sf is None or len(codigo) != 6:
        bloqueo_acceso.registrar_fallo(nombre)
        return False
    totp = pyotp.TOTP(sf.secreto)
    paso_actual = int((ahora if ahora is not None else time.time()) // PASO)
    for desplazamiento in (0, -1, 1):
        paso = paso_actual + desplazamiento
        if paso > sf.ultimo_paso and hmac.compare_digest(totp.at(paso * PASO), codigo):
            primera_vez = not sf.confirmado
            sf.ultimo_paso, sf.confirmado, sf.visible_en_pantalla = paso, True, False
            sf.save(update_fields=["ultimo_paso", "confirmado", "visible_en_pantalla"])
            bloqueo_acceso.limpiar(nombre)
            auditoria.registrar("2fa.activado" if primera_vez else "2fa.verificado", usuario=usuario, entidad="Usuario", entidad_id=usuario.pk)
            return True
    bloqueada = bloqueo_acceso.registrar_fallo(nombre)
    auditoria.registrar("2fa.fallido", usuario=usuario, entidad="Usuario", entidad_id=usuario.pk, motivo="La cuenta queda bloqueada 15 minutos." if bloqueada else "")
    return False
