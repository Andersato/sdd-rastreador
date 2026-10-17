"""API web de solo lectura sobre la base de precios (`prices-api`).

Depende de `src.ingestion` (versión del esquema, reglas del intervalo); la
ingesta y las copias no saben nada de la API ni cargan FastAPI.

Fuente: Ministerio de Industria, Comercio y Turismo - Precios de carburantes
en estaciones de servicio.
"""
