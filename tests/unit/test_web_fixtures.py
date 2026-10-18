"""Las respuestas fijas de la web están completas y al día (add-map-view, 1.4)."""

import json

from tests.fixtures.web.make_web_fixtures import build
from tests.web_fixtures import FIXTURES


def test_every_fixture_has_status_and_body():
    files = sorted(FIXTURES.glob("*.json"))
    assert files
    for path in files:
        spec = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(spec["status"], int), path.name
        assert ("body" in spec) != ("body_text" in spec), path.name


def test_fixtures_match_the_generator():
    """Ningún archivo se ha editado a mano sin pasar por el generador."""
    expected = build()
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(expected)
    for name, spec in expected.items():
        on_disk = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        assert on_disk == spec, name
