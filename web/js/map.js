// Todo lo que toca Leaflet (design.md D7). Leaflet se carga como script
// clásico y deja el global `L`. La ficha no es un globo de Leaflet: es una
// hoja de la página (view.js); aquí solo se encuadra el mapa.
import {formatPriceShort} from './logic.js';

const L = window.L;
const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
const MINISTRY = 'Datos: Ministerio de Industria, Comercio y Turismo - Precios de carburantes en estaciones de servicio';
// Península y Baleares: los rectángulos de esas zonas de la API (src/api/geo.py).
export const SPAIN_BOUNDS = [[35.9, -9.4], [43.9, 4.4]];
const MARGIN = 16;

// `covers()` devuelve lo que tapa el mapa en ese momento:
// {top, bottom} en píxeles (caja de atribuciones arriba, hoja abajo).
export function createMap(element, {onClick, onMarker, covers}) {
  const map = L.map(element, {zoomControl: false, attributionControl: false, maxZoom: 19,
    worldCopyJump: false});
  // Atribuciones y zoom en la misma esquina: Leaflet los apila, sin solaparse.
  const attribution = L.control.attribution({position: 'topleft', prefix: false}).addTo(map);
  attribution.addAttribution(MINISTRY);
  L.control.zoom({position: 'topleft', zoomInTitle: 'Acercar', zoomOutTitle: 'Alejar'}).addTo(map);
  L.tileLayer(TILES, {maxZoom: 19, attribution: OSM_ATTRIBUTION}).addTo(map);
  const attributionBox = attribution.getContainer();

  let pointMarker = null;
  let circle = null;
  const markers = new Map();
  let selected = null;

  map.on('click', (event) => onClick(event.latlng.lat, event.latlng.lng));

  // Relleno de los encuadres: la zona visible del mapa (spec, «Mapa a
  // pantalla completa en el móvil»). El zoom no se descuenta.
  function padding() {
    const mapBox = element.getBoundingClientRect();
    const boxBottom = attributionBox.getBoundingClientRect().bottom - mapBox.top;
    const {bottom} = covers();
    return {
      paddingTopLeft: [MARGIN, Math.max(MARGIN, boxBottom + MARGIN)],
      paddingBottomRight: [MARGIN, Math.max(MARGIN, bottom + MARGIN)],
    };
  }

  function fit(bounds) {
    map.fitBounds(bounds, {...padding(), animate: false});
  }

  function clearPoint() {
    if (pointMarker) pointMarker.remove();
    if (circle) circle.remove();
    pointMarker = null;
    circle = null;
  }

  return {
    leaflet: map,
    padding,

    showSpain() {
      fit(SPAIN_BOUNDS);
    },

    // Marca el punto de búsqueda, dibuja el radio y encuadra el círculo.
    setPoint(point, radiusKm) {
      clearPoint();
      const at = [point.lat, point.lon];
      circle = L.circle(at, {radius: radiusKm * 1000, interactive: false, color: '#1f2328',
        weight: 2, fillOpacity: 0.05}).addTo(map);
      pointMarker = L.circleMarker(at, {radius: 7, interactive: false, color: '#ffffff', weight: 3,
        fillColor: '#1f2328', fillOpacity: 1, className: 'search-point'}).addTo(map);
      fit(circle.getBounds());
    },

    clearPoint,

    hasPoint() {
      return pointMarker !== null;
    },

    fitCircle() {
      if (circle) fit(circle.getBounds());
    },

    // Mete el marcador `id` en la zona visible sin cambiar el zoom.
    showMarker(id) {
      const marker = markers.get(String(id));
      if (!marker) return;
      map.panInside(marker.getLatLng(), {...padding(), animate: false});
    },

    // Tras un cambio de tamaño (giro): recalcula y vuelve a encuadrar.
    refresh(selectedId) {
      map.invalidateSize({animate: false});
      if (selectedId && markers.has(String(selectedId))) this.showMarker(selectedId);
      else if (circle) fit(circle.getBounds());
      else fit(SPAIN_BOUNDS);
    },

    setStations(stations, tiers) {
      this.clearStations();
      stations.forEach((station, index) => {
        const label = document.createElement('span');
        label.className = `label tier-${tiers[index]}`;
        label.textContent = formatPriceShort(station.price);
        const icon = L.divIcon({className: 'price-marker', html: label, iconSize: null});
        const marker = L.marker([station.latitude, station.longitude], {icon, keyboard: false})
          .addTo(map);
        marker.getElement().dataset.id = String(station.id);
        marker.on('click', () => onMarker(station.id));
        markers.set(String(station.id), marker);
      });
    },

    clearStations() {
      for (const marker of markers.values()) marker.remove();
      markers.clear();
      selected = null;
    },

    select(id) {
      if (selected) {
        const old = markers.get(selected);
        if (old) {
          old.getElement().classList.remove('selected');
          old.setZIndexOffset(0);
        }
      }
      selected = id === null ? null : String(id);
      const marker = selected ? markers.get(selected) : null;
      if (marker) {
        marker.getElement().classList.add('selected');
        marker.setZIndexOffset(1000);
      }
    },
  };
}
