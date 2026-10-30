import os

os.environ.setdefault("PLANIFICACION_ENTORNO", "desarrollo")

import pytest


@pytest.fixture(autouse=True)
def _hash_rapido_solo_en_pruebas(settings):
    """Las pruebas crean muchos usuarios; el hash de producción (lento a propósito) no aporta nada aquí."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
