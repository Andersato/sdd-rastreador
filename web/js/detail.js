// Detalles de la ficha por búsqueda (add-station-detail, design.md D6): como
// mucho una petición por gasolinera y búsqueda, más una por cada «Reintentar».
// No toca el DOM; avisa con `onChange(id)` cuando cambia una entrada.
import {isText, parseDetail} from './logic.js';

export function stationPath(id) {
  return `/api/stations/${encodeURIComponent(id)}`;
}

// Entrada: {status: 'loading' | 'ok' | 'error', result, retryAt, retryable}.
// `result` es la salida de `parseDetail` (ok) o la clasificación del error.
export function createDetailLoader({fetchOne, now = () => Date.now(), onChange = () => {}}) {
  let entries = new Map();
  let controller = new AbortController();
  let generation = 0;
  let fuelSlug = null;

  function errorEntry(result, {retryAt = 0, retryable = true} = {}) {
    return {status: 'error', result, retryAt, retryable};
  }

  function settle(id, mine, result) {
    if (mine !== generation || result.kind === 'aborted') return;
    let entry;
    if (result.kind === 'ok') {
      const parsed = parseDetail(result.body, id, fuelSlug);
      entry = parsed.ok ? {status: 'ok', result: parsed, retryAt: 0, retryable: false}
        : errorEntry({kind: 'unexpected'});
    } else if (result.kind === 'busy') {
      entry = errorEntry(result, {retryAt: now() + result.seconds * 1000});
    } else {
      entry = errorEntry(result);
    }
    entries.set(id, entry);
    onChange(id);
  }

  function launch(id) {
    const mine = generation;
    const entry = {status: 'loading', result: null, retryAt: 0, retryable: false};
    entries.set(id, entry);
    let pending;
    try {
      pending = Promise.resolve(fetchOne(stationPath(id), controller.signal));
    } catch {
      pending = Promise.resolve({kind: 'unreachable'});
    }
    pending.catch(() => ({kind: 'unreachable'})).then((result) => settle(id, mine, result));
    return entry;
  }

  return {
    // Búsqueda nueva: se olvidan los detalles y se descartan los que llegan.
    reset(slug) {
      controller.abort();
      controller = new AbortController();
      entries = new Map();
      generation += 1;
      fuelSlug = slug;
    },

    get(id) {
      return isText(id) ? entries.get(id) || null : null;
    },

    // Entrada de la gasolinera; pide su detalle solo si aún no lo tiene.
    open(station) {
      const id = station.id;
      if (!isText(id)) return errorEntry({kind: 'unexpected'}, {retryable: false});
      return entries.get(id) || launch(id);
    },

    // «Reintentar»: solo con un error reintentable y pasado su `Retry-After`.
    retry(id) {
      const entry = this.get(id);
      if (!entry || entry.status !== 'error' || !entry.retryable || now() < entry.retryAt) {
        return entry;
      }
      return launch(id);
    },
  };
}
