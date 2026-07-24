"""API keys por integración: hash, scopes propios e identidad (Chunk 2).

Lo puro (generar/hashear/parsear) va sin DB. La resolución contra Postgres se prueba en el
e2e (`tests/e2e/test_api_keys_e2e.py`), contra el stack levantado.
"""
from teleflow.gateway import auth
from teleflow.gateway.auth import generar_key, hash_key


def test_la_key_generada_es_aleatoria_y_no_adivinable():
    a, b = generar_key(), generar_key()

    assert a != b
    assert a.startswith("tf_")
    assert len(a) > 40          # 32 bytes en base64url


def test_hash_estable_y_la_key_no_se_puede_recuperar():
    key = "tf_secreto"

    digest = hash_key(key)

    assert digest == hash_key(key)            # determinista: sirve para buscar por hash
    assert key not in digest                  # no es reversible ni contiene el secreto
    assert len(digest) == 64                  # sha256 hex
    assert hash_key("tf_secretO") != digest   # sensible a cualquier cambio


def test_keys_admin_es_un_scope_mas_y_no_lo_da_una_key_comun():
    """Repartir permisos es un permiso: keys:admin no viene de arrastre con nada."""
    assert auth.KEYS_ADMIN in auth.ALL_SCOPES
    assert auth.KEYS_ADMIN not in auth.parse_scopes("flows:deploy,entities:write")
    assert auth.KEYS_ADMIN in auth.parse_scopes("*")
