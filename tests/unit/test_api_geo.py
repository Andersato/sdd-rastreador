"""«Coordenadas fuera de España» y distancias de «Gasolineras cercanas» (D6)."""

import pytest

from src.api.geo import distance_km, in_spain

MADRID = (40.416775, -3.703790)


@pytest.mark.parametrize(("lat", "lon"), [
    (40.4168, -3.7038),     # Madrid
    (28.1235, -15.4363),    # Las Palmas de Gran Canaria
    (39.5696, 2.6502),      # Palma
    (35.8894, -5.3213),     # Ceuta
    (35.2923, -2.9381),     # Melilla
    (42.0, -9.30),          # Galicia, dentro del rectángulo
    (38.7223, -9.1393),     # Lisboa: dentro del rectángulo de la Península (aceptado)
    (35.9, -9.4), (43.9, 3.4),        # esquinas de la Península
    (27.6, -18.2), (29.5, -13.3),     # esquinas de Canarias
])
def test_points_in_spain(lat, lon):
    assert in_spain(lat, lon)


@pytest.mark.parametrize(("lat", "lon"), [
    (0.0, 0.0),                  # estación "11988"
    (-8.659472, 42.037472),      # Tui con latitud y longitud intercambiadas
    (42.0, -9.45),               # en el mar, al oeste de la Península
    (48.8566, 2.3522),           # París
    (43.9001, 0.0),              # justo al norte
    (None, -3.7), (40.4, None),
])
def test_points_outside_spain(lat, lon):
    assert not in_spain(lat, lon)


@pytest.mark.parametrize(("point", "km"), [
    ((40.4250, -3.7038), 0.91),
    ((40.4168, -3.6800), 2.01),
    ((40.4400, -3.7300), 3.40),
    ((40.4630, -3.7038), 5.14),
])
def test_madrid_distances(point, km):
    """Escenario: Búsqueda en Madrid."""
    assert round(distance_km(*MADRID, *point), 2) == km


def test_zone_filter_distances():
    """Escenario: Estación justo fuera de una zona."""
    assert round(distance_km(42.0, -9.35, 42.0, -9.30), 2) == 4.13
    assert round(distance_km(42.0, -9.35, 42.0, -9.45), 2) == 8.26


def test_same_point_is_zero():
    assert distance_km(*MADRID, *MADRID) == 0
