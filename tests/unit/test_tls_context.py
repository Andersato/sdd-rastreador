"""Requisitos «Cifrados ofrecidos al conectar con la API» y «Verificación del
certificado de la API»: configuración del contexto TLS, comparada con el
contexto por defecto de Python en la misma máquina (sin red)."""

import ssl

from src.ingestion.client import tls_context
from tests.helpers import REPO_ROOT

EXTRA = {"AES256-GCM-SHA384", "AES128-GCM-SHA256"}


def names(ctx, tls13):
    return {c["name"] for c in ctx.get_ciphers() if (c["protocol"] == "TLSv1.3") == tls13}


def all_names(ctx):
    return {c["name"] for c in ctx.get_ciphers()}


def test_keeps_default_ciphers_and_adds_only_the_two():
    default, ours = ssl.create_default_context(), tls_context()
    assert all_names(default) <= all_names(ours)
    added = all_names(ours) - all_names(default)
    assert added <= EXTRA
    if len(all_names(default)) == 17 and not (all_names(default) & EXTRA):
        # Python 3.12 con OpenSSL 3.0.22 (imagen) o 3.6.3 (.venv).
        assert added == EXTRA


def test_weak_ciphers_not_offered():
    ours = all_names(tls_context())
    assert "AES256-SHA" not in ours
    assert "AES256-SHA256" not in ours


def test_tls13_ciphers_unchanged():
    assert names(tls_context(), tls13=True) == names(ssl.create_default_context(), tls13=True)


def test_minimum_version_is_tls12_and_security_level_unchanged():
    default, ours = ssl.create_default_context(), tls_context()
    assert ours.minimum_version == default.minimum_version == ssl.TLSVersion.TLSv1_2
    assert ours.security_level == default.security_level


def test_certificate_and_hostname_verification_active():
    ours = tls_context()
    assert ours.verify_mode == ssl.CERT_REQUIRED
    assert ours.check_hostname is True


def test_ssl_cert_file_only_in_tests():
    """La variable con la que los tests confían en la autoridad de prueba
    nunca puede fijarse en lo que usa la ingesta real (design, decisión 6)."""
    files = [REPO_ROOT / "Dockerfile", REPO_ROOT / "docker-compose.yml"]
    for folder in ("src", "container"):
        files += sorted(
            f for f in (REPO_ROOT / folder).rglob("*")
            if f.is_file() and "__pycache__" not in f.parts
        )
    offenders = [
        str(f.relative_to(REPO_ROOT))
        for f in files
        if contains_var(f.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def contains_var(text):
    return "SSL_CERT_FILE" in text


def test_ssl_cert_file_check_detects_the_variable():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert not contains_var(dockerfile)
    assert contains_var(dockerfile + "\nENV SSL_CERT_FILE=/x/ca.pem\n")


# --- Refuerzos -------------------------------------------------------------


def test_extra_ciphers_go_after_the_default_ones():
    """Design, decisión 1 (orden): los dos cifrados RSA van al final, para que
    con un servidor que admite ECDHE se siga prefiriendo un cifrado por defecto."""
    ours = [c["name"] for c in tls_context().get_ciphers() if c["protocol"] != "TLSv1.3"]
    default = names(ssl.create_default_context(), tls13=False)
    added = [n for n in ours if n not in default]
    assert added and ours[-len(added):] == added


def test_maximum_version_and_options_unchanged():
    """Requisito «Cifrados ofrecidos…»: solo cambia la lista de TLS 1.2; la
    versión máxima y las opciones (p. ej. sin SSLv3/TLS 1.0) quedan igual."""
    default, ours = ssl.create_default_context(), tls_context()
    assert ours.maximum_version == default.maximum_version
    assert ours.options == default.options


def test_trusts_the_same_authorities_and_flags_as_default():
    """Escenario: Verificación activa en la configuración. Requisito: verificar
    contra las autoridades de confianza que Python usa por defecto (sin `cafile`
    propio) y con las mismas comprobaciones (p. ej. VERIFY_X509_STRICT)."""
    default, ours = ssl.create_default_context(), tls_context()
    assert ours.cert_store_stats() == default.cert_store_stats()
    assert ours.get_ca_certs() == default.get_ca_certs()
    assert ours.verify_flags == default.verify_flags


def test_download_passes_a_new_tls_context_to_urlopen(monkeypatch):
    """Requisito «Cifrados ofrecidos…» para la URL por defecto (y cualquier otra):
    `_download` pasa a `urlopen` el contexto de `tls_context()`, uno nuevo en
    cada descarga. Sin red: `urlopen` está simulado."""
    from src.ingestion import client

    contexts, urls = [], []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout=None, context=None):
        urls.append(request.full_url)
        contexts.append(context)
        return FakeResponse()

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    assert client._download(client.API_URL, 5) == b'{"ok": true}'
    assert client._download("https://127.0.0.1:1/api", 5) == b'{"ok": true}'
    assert urls == [client.API_URL, "https://127.0.0.1:1/api"]
    for ctx in contexts:
        assert isinstance(ctx, ssl.SSLContext)
        assert EXTRA <= all_names(ctx)
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert contexts[0] is not contexts[1]


def strict_default_context(level):
    """Contexto por defecto de una máquina con una política más estricta."""
    real = ssl.create_default_context

    def create():
        ctx = real()
        ctx.set_ciphers(f"DEFAULT:@SECLEVEL={level}")
        return ctx

    return create


def test_security_level_never_lowered(monkeypatch):
    from src.ingestion import client

    monkeypatch.setattr(client.ssl, "create_default_context", strict_default_context(3))
    assert client.tls_context().security_level == 3


def test_security_level_at_least_two(monkeypatch):
    from src.ingestion import client

    monkeypatch.setattr(client.ssl, "create_default_context", strict_default_context(1))
    assert client.tls_context().security_level == 2
