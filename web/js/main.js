// Arranque y estado de la página (design.md D5 y D6).
import {createSearcher, nearbyPath, request} from './api.js';
import {createDetailLoader} from './detail.js';
import {
  DEFAULT_RADIUS, RADII, captureText, directionsLink, discardedText, emptyText, mapsProvider,
  moreText, newerCaptureText, searchPoint, staleText, stationsCountText, tiers, validFuels,
  validStations,
} from './logic.js';
import {createMap} from './map.js';
import {loadPrefs, savePref} from './storage.js';
import {MESSAGES, createView, errorText, rowText} from './view.js';

const LOCATION_WAIT_MS = 10000;

const state = {
  fuels: [], // combustibles ofrecidos (con estaciones), en el orden de la API
  fuelsReady: false,
  fuel: null,
  radius: DEFAULT_RADIUS,
  point: null, // punto de búsqueda redondeado {lat, lon}
  pointFromLocation: false,
  location: null, // ubicación del navegador, redondeada
  waitingLocation: true,
  userClicked: false, // no se borra aunque el punto se quite tras un 422
  stations: [],
  unit: '€/l',
  selected: null,
  detailSource: null, // 'row' | 'marker' | 'cheapest'
  searchCapture: null, // `capture` de la última búsqueda correcta (add-station-detail, D4)
};

const prefs = loadPrefs();
const searcher = createSearcher();
let retryAction = null;

const view = createView({
  onRetry: () => retryAction && retryAction(),
  onRow: (id) => select(id, 'row'),
  onCheapest: () => state.stations.length && select(state.stations[0].id, 'cheapest'),
  onCloseDetail: () => closeDetail(true),
  onDetailRetry: () => retryDetail(),
});
// Detalles de la ficha, uno por gasolinera y búsqueda (add-station-detail, D6).
const detail = createDetailLoader({fetchOne: request, onChange: (id) => onDetailChange(id)});
const {fuel: fuelSelect, radius: radiusSelect, back, toggle, cheapest} = view.elements;
const map = createMap(view.elements.map, {
  onClick: (lat, lon) => onMapClick(lat, lon),
  onMarker: (id) => select(id, 'marker'),
  covers: () => ({bottom: view.sheetCover()}),
});

// --- avisos y errores ----------------------------------------------------------

function fail(result, retry) {
  retryAction = retry;
  view.showMessage(errorText(result), result.kind === 'busy' ? {retryAfter: result.seconds} : {});
}

// Quita los resultados; `fold` pliega la hoja (búsqueda que se queda sin lista).
function clearStations({fold = false} = {}) {
  closeDetail(false);
  detail.reset(state.fuel);
  state.searchCapture = null;
  state.stations = [];
  map.clearStations();
  view.clearResults({fold});
}

// --- combustibles y salud ----------------------------------------------------------

async function loadFuels() {
  state.fuelsReady = false;
  fuelSelect.disabled = true;
  view.clearMessage();
  const result = await request('/api/fuels');
  if (result.kind !== 'ok') {
    fail(result, loadFuels);
    return;
  }
  const valid = validFuels(result.body.data);
  if (!valid || valid.all.length === 0) {
    fail({kind: 'unexpected'}, loadFuels);
    return;
  }
  if (valid.offered.length === 0) {
    retryAction = loadFuels;
    view.showMessage(MESSAGES.no_prices);
    return;
  }
  state.fuels = valid.offered;
  const options = state.fuels.map((fuel) => {
    const option = document.createElement('option');
    option.value = fuel.slug;
    option.textContent = `${fuel.name} (${fuel.unit})`;
    return option;
  });
  fuelSelect.replaceChildren(...options);
  const wanted = state.fuel || prefs.fuel;
  state.fuel = state.fuels.some((f) => f.slug === wanted) ? wanted : state.fuels[0].slug;
  fuelSelect.value = state.fuel;
  fuelSelect.disabled = false;
  state.fuelsReady = true;
  if (state.point) search();
}

async function loadHealth() {
  const result = await request('/api/health');
  if (result.kind === 'ok' && result.body.status === 'desactualizada') {
    view.showStale(staleText(result.body.capture));
  }
}

// --- búsqueda -----------------------------------------------------------------------

function currentFuel() {
  return state.fuels.find((f) => f.slug === state.fuel) || state.fuels[0];
}

async function search() {
  if (!state.point || !state.fuelsReady) return;
  const fuel = currentFuel();
  clearStations();
  view.clearMessage();
  const point = state.point;
  const radius = state.radius;
  const result = await searcher.run(nearbyPath({...point, fuel: fuel.slug, radius}));
  if (result.kind === 'stale' || result.kind === 'aborted') return;
  showResult(result, fuel, radius);
  // La hoja cambia de alto al llenarse: el círculo se vuelve a encuadrar.
  map.fitCircle();
}

function showResult(result, fuel, radius) {
  if (result.kind === 'outside_spain') {
    outsideSpain();
    return;
  }
  if (result.kind === 'unknown_fuel') {
    clearStations({fold: true});
    fail(result, loadFuels);
    return;
  }
  if (result.kind !== 'ok') {
    clearStations({fold: true});
    fail(result, search);
    return;
  }
  const data = result.body.data;
  const valid = data && typeof data === 'object' ? validStations(data.stations) : null;
  if (!valid) {
    clearStations({fold: true});
    fail({kind: 'unexpected'}, search);
    return;
  }
  const total = typeof data.total === 'number' ? data.total : data.stations.length;
  if (data.stations.length === 0 && total === 0) {
    clearStations({fold: true});
    retryAction = null;
    view.showMessage(emptyText(fuel.name, radius), {retryable: false});
    return;
  }
  if (valid.shown.length === 0) {
    clearStations({fold: true});
    fail({kind: 'unexpected'}, search);
    return;
  }
  showStations(valid, total, data.stations.length, fuel, radius, result.body.capture);
}

function showStations(valid, total, received, fuel, radius, capture) {
  const stations = valid.shown;
  const unit = typeof stations[0].unit === 'string' ? stations[0].unit : fuel.unit;
  const colours = tiers(stations.map((s) => s.price));
  state.stations = stations;
  state.unit = unit;
  state.searchCapture = capture;
  view.renderStations(stations, colours, unit);
  map.setStations(stations, colours);
  const prices = stations.map((s) => s.price);
  view.showLegend({count: stations.length, tiers: colours, min: Math.min(...prices),
    max: Math.max(...prices), unit});
  view.showSummary({
    count: stationsCountText(stations.length),
    more: total > received ? moreText(total, received, radius) : null,
    discarded: valid.discarded > 0 ? discardedText(valid.discarded) : null,
    capture: captureText(capture),
    cheapestText: rowText(stations[0], unit),
  });
}

function outsideSpain() {
  const fromLocation = state.pointFromLocation;
  state.point = null;
  map.clearPoint();
  clearStations({fold: true});
  retryAction = null;
  view.showMessage(MESSAGES.outside_spain, {retryable: false});
  if (fromLocation) {
    map.showSpain();
    if (document.activeElement === back) view.elements.status.focus();
    back.hidden = true;
  }
}

function usePoint(point, fromLocation) {
  state.point = point;
  state.pointFromLocation = fromLocation;
  closeDetail(false);
  map.setPoint(point, state.radius);
  search();
}

// --- ubicación ------------------------------------------------------------------------

function onMapClick(lat, lon) {
  state.userClicked = true;
  if (!state.waitingLocation) view.setHint(null);
  usePoint(searchPoint(lat, lon), false);
}

function onLocation(position) {
  const {latitude, longitude} = position.coords;
  state.location = searchPoint(latitude, longitude);
  state.waitingLocation = false;
  view.setHint(null);
  back.hidden = false;
  if (!state.userClicked) usePoint(state.location, true);
}

function onNoLocation() {
  if (!state.waitingLocation) return;
  state.waitingLocation = false;
  if (state.userClicked) {
    view.setHint(null);
  } else {
    view.setHint(MESSAGES.click);
    map.showSpain();
  }
}

function requestLocation() {
  view.setHint(MESSAGES.searching);
  const geolocation = navigator.geolocation;
  if (!geolocation || typeof geolocation.getCurrentPosition !== 'function') {
    onNoLocation();
    return;
  }
  // Plazo propio de 10 s desde la petición: el tiempo del aviso de permiso
  // no lo cuenta el `timeout` nativo.
  const timer = setTimeout(onNoLocation, LOCATION_WAIT_MS);
  try {
    geolocation.getCurrentPosition(
      (position) => {
        clearTimeout(timer);
        onLocation(position);
      },
      () => {
        clearTimeout(timer);
        onNoLocation();
      },
      {enableHighAccuracy: false, maximumAge: 600000},
    );
  } catch {
    clearTimeout(timer);
    onNoLocation();
  }
}

// --- selección y ficha ------------------------------------------------------------------

function select(id, source) {
  const station = state.stations.find((s) => String(s.id) === String(id));
  if (!station) return;
  state.selected = String(station.id);
  state.detailSource = source;
  // Primero la ficha: en escritorio cambia el alto del panel antes de desplazar la lista.
  view.openDetail(station, state.unit);
  view.setDirections(directionsLink(mapsProvider(navigator.userAgent), station.latitude,
    station.longitude));
  renderDetail(detail.open(station));
  view.highlight(state.selected, {scroll: source === 'marker'});
  map.select(state.selected);
  map.showMarker(state.selected);
}

// Pinta el detalle de la ficha abierta. Cuando ya tiene su alto, el marcador
// vuelve a la zona visible (D10) y, en escritorio, la lista se desplaza otra
// vez hasta su fila si se abrió desde el marcador: la ficha puede haber crecido.
function renderDetail(entry) {
  const newer = entry.status === 'ok'
    ? newerCaptureText(state.searchCapture, entry.result.capture) : null;
  view.renderDetail(entry, {newer, onPainted: () => {
    if (!state.selected) return;
    view.highlight(state.selected, {scroll: state.detailSource === 'marker'});
    map.showMarker(state.selected);
  }});
}

// Llega el detalle de `id`: solo se pinta si es la ficha abierta.
function onDetailChange(id) {
  if (state.selected !== id || !view.detailOpen()) return;
  renderDetail(detail.get(id));
}

function retryDetail() {
  const entry = state.selected ? detail.retry(state.selected) : null;
  if (!entry) return;
  renderDetail(entry);
  view.focusDetailStatus();
}

// Cierra la ficha; con `returnFocus`, el foco vuelve a donde se abrió (D10).
function closeDetail(returnFocus) {
  const id = state.selected;
  const source = state.detailSource;
  state.selected = null;
  state.detailSource = null;
  view.highlight(null);
  map.select(null);
  if (!view.detailOpen()) return;
  view.closeDetail();
  if (!returnFocus || !id) return;
  if (source === 'cheapest' && !view.isDesktop()) {
    cheapest.focus();
  } else if (view.listVisible()) {
    const row = view.row(id);
    if (row) row.focus();
  } else {
    toggle.focus();
  }
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && view.detailOpen()) closeDetail(true);
});

// --- controles --------------------------------------------------------------------------

fuelSelect.addEventListener('change', () => {
  state.fuel = fuelSelect.value;
  savePref('fuel', state.fuel);
  if (state.point) search();
});

radiusSelect.addEventListener('change', () => {
  state.radius = Number(radiusSelect.value);
  savePref('radius', state.radius);
  if (state.point) {
    closeDetail(false);
    map.setPoint(state.point, state.radius);
    search();
  }
});

back.addEventListener('click', () => {
  if (state.location) usePoint(state.location, true);
});

document.getElementById('controls').addEventListener('submit', (event) => event.preventDefault());

// Giro o cambio de tamaño: reencuadre sin peticiones (D10).
let resizeFrame = 0;
function onResize() {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => map.refresh(state.selected));
}
window.addEventListener('resize', onResize);
window.addEventListener('orientationchange', onResize);

// --- arranque ---------------------------------------------------------------------------

const savedRadius = Number(prefs.radius);
state.radius = RADII.includes(savedRadius) ? savedRadius : DEFAULT_RADIUS;
radiusSelect.value = String(state.radius);
view.setHint(MESSAGES.searching);
map.showSpain();
loadHealth();
loadFuels();
requestLocation();

// Para los tests y para depurar: el estado de la página y el mapa.
window.__mapView = {state, map, detail};
