"""Zonas de España y distancia en línea recta (design.md, D6).

Las zonas son rectángulos de latitud y longitud, extremos incluidos. Incluyen
parte de Portugal, Francia, Andorra y Marruecos: se acepta (proposal.md).
"""

import math

EARTH_RADIUS_KM = 6371.0

# (latitud mínima, latitud máxima, longitud mínima, longitud máxima)
ZONES = {
    "Península": (35.9, 43.9, -9.4, 3.4),
    "Baleares": (38.6, 40.1, 1.1, 4.4),
    "Canarias": (27.6, 29.5, -18.2, -13.3),
    "Ceuta": (35.86, 35.93, -5.39, -5.27),
    "Melilla": (35.26, 35.32, -2.98, -2.92),
}


def in_spain(latitude: float | None, longitude: float | None) -> bool:
    """True si el punto cae en alguna de las zonas de España."""
    if latitude is None or longitude is None:
        return False
    return any(lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max
               for lat_min, lat_max, lon_min, lon_max in ZONES.values())


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia haversine sobre una esfera de 6371 km de radio."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
