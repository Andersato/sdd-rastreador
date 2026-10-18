// Peticiones al servidor (design.md D5): tiempo límite de 15 s, una búsqueda
// a la vez y clasificación de cada respuesta. No toca el DOM ni Leaflet.
import {coordParam, retryAfterSeconds} from './logic.js';

export const TIMEOUT_MS = 15000;
export const LIMIT = 100;
const BUSY_CODES = new Set(['api_ocupada', 'base_ocupada', 'consulta_demasiado_larga']);

function errorOf(body) {
  if (!body || typeof body !== 'object' || !body.error || typeof body.error !== 'object') return null;
  return body.error;
}

// Clasifica una respuesta ya recibida: `{kind, …}` con kind en
// ok | busy | no_data | outside_spain | unknown_fuel | server_error | unexpected.
export function classify(status, retryAfter, text) {
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return {kind: 'unexpected'};
  }
  if (status >= 200 && status < 300) {
    return body && typeof body === 'object' ? {kind: 'ok', body} : {kind: 'unexpected'};
  }
  const error = errorOf(body);
  const code = error && typeof error.code === 'string' ? error.code : null;
  if (status === 503 && BUSY_CODES.has(code)) {
    return {kind: 'busy', seconds: retryAfterSeconds(retryAfter)};
  }
  if (status === 503) {
    const message = error && typeof error.message === 'string' ? error.message : null;
    return {kind: 'no_data', message};
  }
  if (status === 422 && code === 'fuera_de_espana') return {kind: 'outside_spain'};
  if (status === 422 && code === 'combustible_desconocido') return {kind: 'unknown_fuel'};
  return {kind: 'server_error'};
}

// Pide `path` y devuelve su clasificación; `unreachable` si falla la red o
// pasan 15 s, `aborted` si `signal` la cancela (una búsqueda más nueva).
export async function request(path, signal) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    signal.addEventListener('abort', onAbort);
  }
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: {Accept: 'application/json'},
      cache: 'no-store',
    });
    const text = await response.text();
    return classify(response.status, response.headers.get('Retry-After'), text);
  } catch {
    if (signal && signal.aborted && !timedOut) return {kind: 'aborted'};
    return {kind: 'unreachable'};
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', onAbort);
  }
}

export function nearbyPath({lat, lon, fuel, radius}) {
  const params = new URLSearchParams({
    lat: coordParam(lat), lon: coordParam(lon), fuel, radius_km: String(radius),
    limit: String(LIMIT),
  });
  return `/api/stations/nearby?${params}`;
}

// Una búsqueda a la vez: la nueva cancela la anterior, y una respuesta que
// no es de la última búsqueda se descarta (`stale`).
export function createSearcher(fetchOne = request) {
  let sequence = 0;
  let controller = null;
  return {
    async run(path) {
      sequence += 1;
      const mine = sequence;
      if (controller) controller.abort();
      controller = new AbortController();
      const result = await fetchOne(path, controller.signal);
      if (mine !== sequence) return {kind: 'stale'};
      return result;
    },
  };
}
