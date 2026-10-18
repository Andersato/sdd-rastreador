// Preferencias del navegador (design.md D9): solo el combustible y el radio,
// nunca coordenadas. Si el almacenamiento falla, la página funciona igual.
const KEY = 'precios-gasolineras.preferencias';

export function loadPrefs() {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const value = JSON.parse(raw);
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

// Guarda una sola clave (`fuel` o `radius`) y conserva la otra tal como estaba.
export function savePref(name, value) {
  try {
    const current = loadPrefs();
    current[name] = value;
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Sin almacenamiento: la elección vale solo para esta visita.
  }
}
