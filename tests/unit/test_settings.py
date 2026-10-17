"""`container/settings.py`: lectura de COLLECTION_ENABLED (D8)."""

import importlib.util

import pytest

from tests.helpers import REPO_ROOT

spec = importlib.util.spec_from_file_location("container_settings", REPO_ROOT / "container" / "settings.py")
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


@pytest.mark.parametrize("text", ["true", "TRUE", " true ", "True"])
def test_true_in_any_case_and_spacing_enables(text):
    """Escenario: Formas admitidas."""
    assert settings.parse_enabled(text) is True


@pytest.mark.parametrize("text", [None, "", "false", "FALSE", " false "])
def test_absent_empty_or_false_disables(text):
    """Escenarios: Sin la variable; Variable vacía o false."""
    assert settings.parse_enabled(text) is False


@pytest.mark.parametrize("text", ["yes", "1", "si"])
def test_other_values_are_invalid_and_show_the_value(text):
    """Escenario: Valor no válido."""
    with pytest.raises(settings.InvalidSetting) as exc:
        settings.parse_enabled(text)
    assert repr(text) in str(exc.value)
    assert "solo 'true' activa la recogida" in str(exc.value)


def test_collection_state_texts():
    assert settings.collection_state({"COLLECTION_ENABLED": "true"}) == "recogida activada"
    assert settings.collection_state({}).startswith("recogida desactivada")
    assert "COLLECTION_ENABLED=true" in settings.collection_state({})
    assert settings.collection_state({"COLLECTION_ENABLED": "yes"}) == "COLLECTION_ENABLED no válido ('yes')"
