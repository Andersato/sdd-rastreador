"""Escenarios de prices-api comprobados por HTTP que antes solo se probaban sobre
`read_snapshot` o sobre funciones sueltas (revisión de tests del cambio).

Requisitos: «Base inexistente, vacía o ilegible», «Base ocupada por una
recogida», «La API no impide guardar capturas», «Lecturas de la base de una
en una», «Datos siempre de capturas terminadas», «Formato común de las
respuestas correctas», «Desfase de la fecha de la fuente en el cambio de
hora», «Salud del servicio», «Intervalo no válido en la salud» y «Limpieza
de textos al responder».

Bases siempre en carpetas temporales; nunca ./data ni la API del Ministerio.
"""

import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import src.api.db as api_db
import src.api.queries
from src.ingestion.storage import SCHEMA
from tests.api_helpers import (
    folder_state,
    CAPTURE_AT,
    assert_error,
    basic_db,
    hold_lock,
    make_client,
    priced,
    save,
)
from tests.helpers import check_not_real_data, db_dump
from tests.storage_helpers import make_pending_journal

UTC = timezone.utc
BUSY_MESSAGE = ("la base de datos está ocupada guardando una captura; "
                "inténtalo de nuevo en unos segundos")
SLOW_SQL = ("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
            "SELECT count(*) FROM (SELECT i FROM n LIMIT 100000000)")


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


def schema_only(db):
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.close()


def timed_get(client, path):
    start = time.monotonic()
    response = client.get(path)
    return response, time.monotonic() - start


# --- Base inexistente, vacía o ilegible ---------------------------------------------

@pytest.mark.parametrize("prepare", [schema_only, lambda db: db.write_bytes(b"")],
                         ids=["version-1-sin-capturas", "archivo-0-bytes"])
def test_database_without_captures_by_http(db, prepare):
    """Escenario: Base sin capturas (GET /api/fuels; el archivo no cambia)."""
    prepare(db)
    before = folder_state(db.parent)
    body = assert_error(make_client(db).get("/api/fuels"), 503, "sin_capturas")
    assert "aún no tiene capturas" in body["error"]["message"]
    assert folder_state(db.parent) == before


def test_file_that_is_not_a_database_by_http(db):
    """Escenario: Archivo que no es una base (texto «hola»)."""
    db.write_text("hola")
    body = assert_error(make_client(db).get("/api/fuels"), 503, "base_ilegible")
    assert body["error"]["message"] == "no se ha podido leer la base de datos"
    assert db.read_text() == "hola"


def test_first_capture_with_the_api_running_gives_that_capture(db):
    """Escenario: Primera captura con la API en marcha (200 con esa captura)."""
    client = make_client(db)
    assert_error(client.get("/api/fuels"), 503, "sin_base")
    basic_db(db)
    response = client.get("/api/fuels")
    assert response.status_code == 200
    assert response.json()["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"


def test_restored_database_by_http(db, tmp_path):
    """Escenario: Base restaurada desde una copia (12 capturas, sin reiniciar la API)."""
    basic_db(db)
    client = make_client(db)
    assert client.get("/api/fuels").json()["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    restored = tmp_path / "restaurada.db"
    first = datetime(2026, 10, 17, 1, 17, 2, tzinfo=UTC)
    for n in range(12):
        save(restored, priced("4375", {"Gasoleo A": f"1,{400 + n}"}),
             instant=first + timedelta(hours=6 * n))
    db.rename(db.with_name("prices.db.apartada"))
    shutil.copy2(restored, db)
    body = client.get("/api/stations/4375").json()
    assert body["capture"]["downloaded_at"] == "2026-10-19T19:17:02Z"
    assert body["data"]["prices"][0]["price"] == 1.411


# --- Base ocupada por una recogida ----------------------------------------------------

def test_long_save_by_http(db):
    """Escenario: Guardado más largo que la espera (4 s de bloqueo exclusivo)."""
    basic_db(db)
    client = make_client(db)
    with hold_lock(db, 4):
        response, elapsed = timed_get(client, "/api/fuels")
    body = assert_error(response, 503, "base_ocupada")
    assert body["error"]["message"] == BUSY_MESSAGE
    assert response.headers["retry-after"] == "5"
    assert 1.5 <= elapsed <= 2.5


def test_short_save_by_http(db):
    """Escenario: Guardado corto (0,5 s de bloqueo exclusivo)."""
    basic_db(db)
    client = make_client(db)
    with hold_lock(db, 0.5):
        response, elapsed = timed_get(client, "/api/fuels")
    assert response.status_code == 200, response.text
    assert response.json()["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    assert elapsed <= 1.0


def test_ingestion_preparing_the_capture_by_http(db):
    """Escenario: Recogida preparando la captura (BEGIN IMMEDIATE sin guardar)."""
    basic_db(db)
    client = make_client(db)
    with hold_lock(db, 4, mode="IMMEDIATE"):
        response, elapsed = timed_get(client, "/api/fuels")
    assert response.status_code == 200, response.text
    assert response.json()["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    assert elapsed < 0.5


def test_interrupted_ingestion_by_http(db):
    """Escenario: Recogida que quedó a medias (ni la base ni el diario cambian)."""
    basic_db(db)
    make_pending_journal(db)
    journal = db.with_name("prices.db-journal")
    before = (db.read_bytes(), journal.read_bytes())
    body = assert_error(make_client(db).get("/api/fuels"), 503, "recogida_a_medias")
    assert body["error"]["message"] == ("una recogida quedó a medias; se arreglará en la "
                                        "siguiente recogida de la máquina que recoge")
    assert (db.read_bytes(), journal.read_bytes()) == before


# --- La API no impide guardar capturas / Lecturas de una en una -------------------------

def slow_fuel_counts(reader):
    reader.all(SLOW_SQL)
    raise AssertionError("la consulta lenta no se ha cortado")


def test_cut_query_by_http(db, monkeypatch):
    """Escenario: Consulta cortada (plazo pequeño y consulta lenta inyectada)."""
    basic_db(db)
    monkeypatch.setattr(src.api.queries, "fuel_counts", slow_fuel_counts)
    client = make_client(db, read_options={"read_limit_s": 0.2})
    response, elapsed = timed_get(client, "/api/fuels")
    assert_error(response, 503, "consulta_demasiado_larga")
    assert elapsed < 1.5
    # La base queda libre para escribir inmediatamente después.
    conn = sqlite3.connect(db, timeout=0, isolation_level=None)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_turn_that_does_not_come_by_http(db, monkeypatch):
    """Escenario: Turno que no llega (503 api_ocupada a los 2 s, sin abrir la base)."""
    basic_db(db)
    gate = threading.Lock()
    gate.acquire()  # otra petición tiene el turno
    opened = []
    real_connect = api_db.sqlite3.connect

    def connect(*args, **kwargs):
        opened.append(args)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(api_db.sqlite3, "connect", connect)
    client = make_client(db, read_options={"gate": gate})
    response, elapsed = timed_get(client, "/api/fuels")
    body = assert_error(response, 503, "api_ocupada")
    assert body["error"]["message"] == ("la API está atendiendo demasiadas consultas; "
                                        "inténtalo de nuevo en unos segundos")
    assert response.headers["retry-after"] == "5"
    assert 1.5 <= elapsed <= 2.5
    assert opened == []


def test_turn_held_by_another_request_through_the_app(db, monkeypatch):
    """Escenario: Turno que no llega, con dos peticiones reales a la misma app: la
    primera tiene el turno más de 2 s (lectura lenta) y la segunda da api_ocupada."""
    basic_db(db)
    gate = threading.Lock()
    inside = threading.Event()
    release = threading.Event()

    def held_fuel_counts(reader):
        inside.set()
        release.wait(10)
        return {}

    monkeypatch.setattr(src.api.queries, "fuel_counts", held_fuel_counts)
    client = make_client(db, read_options={"gate": gate, "read_limit_s": 30})
    first = []
    thread = threading.Thread(target=lambda: first.append(client.get("/api/fuels")))
    thread.start()
    try:
        assert inside.wait(10)
        response, elapsed = timed_get(client, "/api/stations/4375")
    finally:
        release.set()
        thread.join(30)
    assert_error(response, 503, "api_ocupada")
    assert response.headers["retry-after"] == "5"
    assert 1.5 <= elapsed <= 2.5
    assert first[0].status_code == 200


# --- Datos siempre de capturas terminadas ----------------------------------------------

# Otro proceso empieza a guardar una captura nueva (fila en snapshots y precios
# nuevos de "4375") sin confirmarla, y la mantiene así `segundos`.
_HALF_SAVE = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
cur = conn.execute("INSERT INTO snapshots (downloaded_at, source_date) "
                   "VALUES ('2026-10-16T13:26:37Z', '2026-10-16T15:26:34')")
conn.execute("INSERT INTO prices VALUES (?, '4375', 'Gasoleo A', 9.999)", (cur.lastrowid,))
print("ready", flush=True)
time.sleep(float(sys.argv[2]))
conn.execute("ROLLBACK")
conn.close()
"""


def half_save(db, seconds):
    check_not_real_data(db)
    proc = subprocess.Popen([sys.executable, "-c", _HALF_SAVE, str(db), str(seconds)],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "ready"
    return proc


@pytest.mark.parametrize("path", ["/api/fuels", "/api/stations/4375",
                                  "/api/provinces/prices?fuel=gasoleo-a",
                                  "/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a",
                                  "/api/health"])
def test_capture_being_saved_is_never_read(db, path):
    """Escenario: Captura guardándose (una recogida a mitad de guardar: 200 con la
    captura terminada del 2026-10-16T07:26:37Z, nunca con parte de la nueva)."""
    basic_db(db)
    client = make_client(db)
    proc = half_save(db, 3)
    try:
        response = client.get(path)
    finally:
        proc.kill()
        proc.wait()
    assert response.status_code == 200, response.text
    assert response.json()["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    assert "9.999" not in response.text


def test_capture_being_saved_with_the_exclusive_lock(db):
    """Escenario: Captura guardándose (con el bloqueo exclusivo: 503 base_ocupada)."""
    basic_db(db)
    with hold_lock(db, 4):
        response = make_client(db, read_options={"busy_timeout_s": 0.3}).get("/api/stations/4375")
    assert_error(response, 503, "base_ocupada")
    assert "9.999" not in response.text


def test_same_source_date_by_http(db):
    """Escenario: Misma Fecha de la API (se usa la descargada a las 07:31:02Z)."""
    save(db, priced("4375", {"Gasoleo A": "1,459"}),
         instant=datetime(2026, 10, 16, 7, 26, 37, tzinfo=UTC))
    save(db, priced("4375", {"Gasoleo A": "1,469"}),
         instant=datetime(2026, 10, 16, 7, 31, 2, tzinfo=UTC))
    body = make_client(db).get("/api/stations/4375").json()
    assert body["capture"] == {"downloaded_at": "2026-10-16T07:31:02Z",
                               "source_date": "2026-10-16T09:26:34+02:00"}
    assert body["data"]["prices"][0]["price"] == 1.469


# --- Fecha de la fuente por HTTP ------------------------------------------------------

@pytest.mark.parametrize(("fecha", "downloaded", "expected"), [
    # Escenario: Fecha de la fuente en horario de invierno.
    ("02/11/2026 06:16:58", datetime(2026, 11, 2, 5, 17, 3, tzinfo=UTC),
     "2026-11-02T06:16:58+01:00"),
    # Escenario: Hora repetida.
    ("25/10/2026 02:30:00", datetime(2026, 10, 25, 1, 31, 0, tzinfo=UTC),
     "2026-10-25T02:30:00+01:00"),
    # Escenario: Hora repetida, primera vez.
    ("25/10/2026 02:30:00", datetime(2026, 10, 25, 0, 31, 0, tzinfo=UTC),
     "2026-10-25T02:30:00+02:00"),
    # Escenario: Hora que no existe.
    ("28/03/2027 02:30:00", datetime(2027, 3, 28, 1, 31, 0, tzinfo=UTC), None),
], ids=["invierno", "hora-repetida", "hora-repetida-primera-vez", "hora-que-no-existe"])
def test_source_date_offset_by_http(db, fecha, downloaded, expected):
    save(db, priced("4375", {"Gasoleo A": "1,459"}), instant=downloaded, fecha=fecha)
    body = make_client(db, now=downloaded).get("/api/fuels").json()
    assert body["capture"]["source_date"] == expected
    assert body["capture"]["downloaded_at"] == downloaded.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Salud del servicio ---------------------------------------------------------------

def test_health_exactly_on_the_threshold(db):
    """Escenario: Justo en el umbral (13 h exactas: ok)."""
    basic_db(db)
    body = make_client(db, now=CAPTURE_AT + timedelta(hours=13)).get("/api/health").json()
    assert body["status"] == "ok"


def test_health_just_over_the_threshold(db):
    basic_db(db)
    body = make_client(db, now=CAPTURE_AT + timedelta(hours=13, seconds=1)).get("/api/health")
    assert body.json()["status"] == "desactualizada"


def test_health_old_capture_with_the_spec_clock(db):
    """Escenario: Captura antigua (2026-10-16T20:27:00Z, la captura de las 07:26:37Z)."""
    basic_db(db)
    now = datetime(2026, 10, 16, 20, 27, 0, tzinfo=UTC)
    response = make_client(db, now=now).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "desactualizada"
    assert body["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"


def test_health_capture_in_the_future(db):
    """Escenario: Captura con fecha en el futuro (2 h por delante del reloj)."""
    basic_db(db)
    body = make_client(db, now=CAPTURE_AT - timedelta(hours=2)).get("/api/health").json()
    assert body["status"] == "ok"


def test_health_accepted_forms(db):
    """Escenario: Formas admitidas (CAPTURE_INTERVAL_HOURS=" 3 " → 7)."""
    basic_db(db)
    body = make_client(db, interval_text=" 3 ").get("/api/health").json()
    assert (body["status"], body["data"]["stale_after_hours"]) == ("ok", 7)


def test_health_invalid_interval_message_names_the_value(db):
    """Escenario: Intervalo imposible (el mensaje dice que se recibió «25»)."""
    basic_db(db)
    message = make_client(db, interval_text="25").get("/api/health").json()["data"]["message"]
    assert "25" in message and "1 a 24" in message


def incompatible(db):
    basic_db(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 2")
    conn.close()


def test_health_error_incompatible(db):
    """Escenario: Errores de la salud (base_no_compatible)."""
    incompatible(db)
    body = assert_error(make_client(db).get("/api/health"), 503, "base_no_compatible")
    assert body["status"] == "error"


def test_health_error_query_too_long(db, monkeypatch):
    """Escenario: Errores de la salud (consulta_demasiado_larga)."""
    basic_db(db)
    monkeypatch.setattr(src.api.queries, "fuel_counts", slow_fuel_counts)
    client = make_client(db, read_options={"read_limit_s": 0.2})
    body = assert_error(client.get("/api/health"), 503, "consulta_demasiado_larga")
    assert body["status"] == "error"


def test_health_error_api_busy(db):
    """Escenario: Errores de la salud (api_ocupada)."""
    basic_db(db)
    gate = threading.Lock()
    gate.acquire()
    client = make_client(db, read_options={"gate": gate, "gate_timeout_s": 0.2})
    response = client.get("/api/health")
    body = assert_error(response, 503, "api_ocupada")
    assert body["status"] == "error"
    assert response.headers["retry-after"] == "5"


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_schedule_is_null_and_database_unchanged(db, value):
    """Escenario: Texto vacío (horario vacío o solo con espacios → null; la base no cambia)."""
    save(db, priced("5120", {"Gasoleo A": "1,459"}, Horario=value))
    before = db_dump(db)
    data = make_client(db).get("/api/stations/5120").json()["data"]
    assert data["schedule"] is None
    assert db_dump(db) == before
