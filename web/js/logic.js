// Lógica pura de la página (design.md D8): formatos, coordenadas, tercios,
// fechas, Retry-After y validación de las respuestas. No toca el DOM ni
// Leaflet, para poder probarla a solas en el navegador.

// Corrige el error binario antes de redondear: 2.05 se guarda como 2.0499…
function clean(x, digits = 12) {
  return Number(x.toPrecision(digits));
}

// Redondeo a `decimals` con la mitad lejos de cero.
function roundHalfAway(x, decimals) {
  const factor = 10 ** decimals;
  const scaled = clean(Math.abs(x) * factor);
  return (Math.sign(x) * Math.round(scaled)) / factor;
}

function comma(text) {
  return text.replace('.', ',');
}

export function formatPrice(price, unit) {
  return `${comma(price.toFixed(3))} ${unit}`;
}

export function formatPriceShort(price) {
  return comma(price.toFixed(3));
}

export function formatDistance(km) {
  return `${comma(roundHalfAway(km, 1).toFixed(1))} km`;
}

export function normalizeLon(lon) {
  const wrapped = (((lon + 180) % 360) + 360) % 360 - 180;
  return clean(wrapped);
}

export function roundCoord(x) {
  const rounded = roundHalfAway(x, 3);
  return Object.is(rounded, -0) ? 0 : rounded;
}

export function coordParam(x) {
  return roundCoord(x).toFixed(3);
}

// Punto de búsqueda a partir de lo que da el mapa o el navegador.
export function searchPoint(lat, lon) {
  return {lat: roundCoord(lat), lon: roundCoord(normalizeLon(lon))};
}

// Tercios de las gasolineras mostradas (spec «Colores por tercios»):
// 'cheap', 'mid', 'expensive' o 'single', en el mismo orden que `prices`.
export function tiers(prices) {
  const milli = prices.map((p) => Math.round(clean(p * 1000)));
  const n = milli.length;
  const distinct = new Set(milli);
  if (distinct.size <= 1) return milli.map(() => 'single');
  const min = Math.min(...milli);
  const max = Math.max(...milli);
  return milli.map((p) => {
    if (p === min) return 'cheap';
    if (p === max) return 'expensive';
    const cheaper = milli.filter((q) => q < p).length;
    const dearer = milli.filter((q) => q > p).length;
    const fewCheaper = 3 * cheaper < n;
    const fewDearer = 3 * dearer < n;
    if (fewCheaper && !fewDearer) return 'cheap';
    if (fewDearer && !fewCheaper) return 'expensive';
    return 'mid';
  });
}

const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const MADRID = new Intl.DateTimeFormat('es-ES', {
  timeZone: 'Europe/Madrid', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

// Instante de una fecha `YYYY-MM-DDTHH:MM:SSZ` en milisegundos, o null.
function utcInstant(iso) {
  if (typeof iso !== 'string' || !ISO_UTC.test(iso)) return null;
  const time = new Date(iso).getTime();
  return Number.isNaN(time) ? null : time;
}

// «16/10/2026 a las 09:26», o null si la fecha no es un instante UTC válido.
export function madridDateTime(iso) {
  const time = utcInstant(iso);
  if (time === null) return null;
  const date = new Date(time);
  const part = {};
  for (const {type, value} of MADRID.formatToParts(date)) part[type] = value;
  return `${part.day}/${part.month}/${part.year} a las ${part.hour}:${part.minute}`;
}

export function captureText(capture) {
  const when = madridDateTime(capture && typeof capture === 'object' ? capture.downloaded_at : null);
  return when ? `Precios de la captura del ${when} (hora de Madrid)` : 'Fecha de la captura desconocida';
}

export function staleText(capture) {
  const when = madridDateTime(capture && typeof capture === 'object' ? capture.downloaded_at : null);
  const base = 'Los precios pueden no estar al día';
  return when ? `${base}: la última captura es del ${when} (hora de Madrid)` : `${base}.`;
}

export const DEFAULT_RETRY_SECONDS = 5;

export function retryAfterSeconds(value) {
  if (typeof value !== 'string' || !/^\d+$/.test(value.trim())) return DEFAULT_RETRY_SECONDS;
  const seconds = Number(value.trim());
  return seconds >= 1 && seconds <= 60 ? seconds : DEFAULT_RETRY_SECONDS;
}

export function isText(x) {
  return typeof x === 'string' && x.trim() !== '';
}

function isNumber(x) {
  return typeof x === 'number' && Number.isFinite(x);
}

// Combustibles que se pueden ofrecer, en el orden de la API; `null` si la
// respuesta no tiene la forma esperada.
export function validFuels(data) {
  if (!Array.isArray(data)) return null;
  const valid = data.filter((f) => f && typeof f === 'object'
    && isText(f.slug) && isText(f.name) && isText(f.unit) && isNumber(f.stations));
  return {all: valid, offered: valid.filter((f) => f.stations > 0)};
}

// Estaciones que se pueden mostrar y cuántas se descartan.
export function validStations(stations) {
  if (!Array.isArray(stations)) return null;
  const shown = stations.filter((s) => s && typeof s === 'object'
    && isNumber(s.price) && isNumber(s.latitude) && isNumber(s.longitude)
    && s.id !== undefined && s.id !== null);
  return {shown, discarded: stations.length - shown.length};
}

export function stationsCountText(n) {
  return n === 1 ? '1 gasolinera encontrada' : `${n} gasolineras encontradas`;
}

export function discardedText(n) {
  return n === 1 ? '1 gasolinera no se muestra por datos incompletos.'
    : `${n} gasolineras no se muestran por datos incompletos.`;
}

export const RADII = [5, 10, 25, 50];
export const DEFAULT_RADIUS = 10;

export function moreText(total, received, radius) {
  const base = `Hay ${total} gasolineras en este radio; se han pedido las ${received} más baratas.`;
  return radius > RADII[0] ? `${base} Reduce el radio para ver menos y más cercanas.` : base;
}

export function emptyText(fuelName, radius) {
  const base = `No hay gasolineras con ${fuelName} a menos de ${radius} km.`;
  return radius < RADII[RADII.length - 1] ? `${base} Prueba con un radio mayor.` : base;
}

// --- ficha de una gasolinera (add-station-detail, design.md D2 a D5) ----------

// Tramos del horario tal como lo publica el Ministerio: partido por «;», sin
// espacios sobrantes ni tramos vacíos. Sin interpretar nada más.
export function scheduleLines(schedule) {
  if (typeof schedule !== 'string') return [];
  return schedule.split(';').map((part) => part.trim()).filter((part) => part !== '');
}

// El combustible buscado primero (marcado `searched`), los demás en su orden.
export function orderPrices(prices, fuelSlug) {
  const index = prices.findIndex((p) => p.slug === fuelSlug);
  if (index < 0) return prices.map((p) => ({...p, searched: false}));
  const rest = prices.filter((_, i) => i !== index).map((p) => ({...p, searched: false}));
  return [{...prices[index], searched: true}, ...rest];
}

function isPrice(p) {
  return p && typeof p === 'object' && isText(p.slug) && isText(p.name) && isText(p.unit)
    && isNumber(p.price) && p.price > 0;
}

// Respuesta de `/api/stations/{id}`: `{ok: true, lines, prices, capture}` o
// `{ok: false}` si no tiene la forma esperada.
export function parseDetail(body, id, fuelSlug) {
  const data = body && typeof body === 'object' ? body.data : null;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return {ok: false};
  if (typeof data.id !== 'string' || data.id !== id) return {ok: false};
  if (!Array.isArray(data.prices)) return {ok: false};
  const valid = data.prices.filter(isPrice);
  if (data.prices.length > 0 && valid.length === 0) return {ok: false};
  return {
    ok: true,
    lines: scheduleLines(data.schedule),
    prices: orderPrices(valid, fuelSlug),
    capture: body.capture && typeof body.capture === 'object' ? body.capture : null,
  };
}

// Aviso si el detalle es de una captura posterior a la de la búsqueda.
export function newerCaptureText(searchCapture, detailCapture) {
  const at = (c) => utcInstant(c && typeof c === 'object' ? c.downloaded_at : null);
  const search = at(searchCapture);
  const detail = at(detailCapture);
  if (search === null || detail === null || detail <= search) return null;
  const when = madridDateTime(detailCapture.downloaded_at);
  return `Horario y precios de una captura más reciente: del ${when} (hora de Madrid)`;
}

// Aplicación de mapas según el agente de usuario: 'google', 'apple' u 'osm'.
export function mapsProvider(userAgent) {
  const ua = String(userAgent || '').toLowerCase();
  if (ua.includes('android')) return 'google';
  if (['iphone', 'ipad', 'ipod', 'macintosh'].some((word) => ua.includes(word))) return 'apple';
  return 'osm';
}

const MAPS_NAMES = {apple: 'Apple Maps', google: 'Google Maps', osm: 'OpenStreetMap'};

// Enlace «Cómo llegar»: solo las coordenadas de la gasolinera, cada una con su
// escritura más corta. Se monta a mano: `URLSearchParams` codificaría la coma.
export function directionsLink(provider, lat, lon) {
  const at = `${String(lat)},${String(lon)}`;
  const hrefs = {
    apple: `https://maps.apple.com/?daddr=${at}`,
    google: `https://www.google.com/maps/dir/?api=1&destination=${at}`,
    osm: `https://www.openstreetmap.org/directions?route=${encodeURIComponent(`;${at}`)}`,
  };
  return {
    href: hrefs[provider],
    label: `Cómo llegar con ${MAPS_NAMES[provider]} (se abre en otra pestaña)`,
  };
}
