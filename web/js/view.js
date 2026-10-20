// DOM de la página (design.md D10): hoja de la lista o panel lateral, ficha,
// avisos, leyenda y foco. Todo texto que llega del servidor se pone con
// `textContent`, nunca como HTML.
import {formatDistance, formatPrice, formatPriceShort} from './logic.js';

const $ = (id) => document.getElementById(id);

function show(element, text) {
  element.textContent = text;
  element.hidden = false;
}

function hide(element) {
  element.textContent = '';
  element.hidden = true;
}

export const MESSAGES = {
  busy: 'El servidor está ocupado; inténtalo en unos segundos',
  unexpected: 'El servidor ha dado una respuesta inesperada',
  server_error: 'El servidor ha dado un error. Inténtalo más tarde.',
  unreachable: 'No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.',
  outside_spain: 'Ese punto está fuera de España. Pincha en el mapa un punto de España.',
  no_prices: 'No hay precios en la última captura',
  searching: 'Buscando tu ubicación…',
  click: 'Pincha en el mapa para elegir dónde buscar',
};

export function noDataText(message) {
  const base = 'No hay datos disponibles.';
  return message ? `${base} Detalle: ${message}` : base;
}

// Texto de un error ya clasificado por `api.js` (add-station-detail, D6). Los
// segundos de `Retry-After` no van en el texto.
export function errorText(result) {
  switch (result.kind) {
    case 'busy':
      return MESSAGES.busy;
    case 'no_data':
      return noDataText(result.message);
    case 'unreachable':
      return MESSAGES.unreachable;
    case 'server_error':
    case 'unknown_fuel':
    case 'outside_spain':
      return MESSAGES.server_error;
    default:
      return MESSAGES.unexpected;
  }
}

export function rowText(station, unit) {
  return `${station.brand || 'Sin rótulo'} · ${formatDistance(station.distance_km)} · ${formatPrice(station.price, unit)}`;
}

const DESKTOP = window.matchMedia('(min-width: 1024px)');

export function createView({onRetry, onRow, onCheapest, onCloseDetail, onDetailRetry}) {
  const panel = $('panel');
  const detail = $('detail');
  const retry = $('retry');
  const toggle = $('toggle');
  const cheapest = $('cheapest');
  const list = $('list');
  let retryTimer = null;
  let detailRetryTimer = null;
  let statusFrame = 0;
  const detailStatus = $('detail-status');
  const detailRetry = $('detail-retry');
  const directions = $('detail-directions');

  retry.addEventListener('click', () => {
    if (!retry.disabled) onRetry();
  });
  list.addEventListener('click', (event) => {
    const row = event.target.closest('.station-row');
    if (row) onRow(row.dataset.id);
  });
  cheapest.addEventListener('click', () => onCheapest());
  $('detail-close').addEventListener('click', () => onCloseDetail());
  detailRetry.addEventListener('click', () => {
    if (!detailRetry.disabled && !detailRetry.hidden) onDetailRetry();
  });

  function cancelDetailTimers() {
    clearTimeout(detailRetryTimer);
    cancelAnimationFrame(statusFrame);
  }

  function listItem(className, text) {
    const item = document.createElement('li');
    item.className = className;
    item.textContent = text;
    return item;
  }

  // Precio de la ficha: «Gasolina 95 E5 · 1,529 €/l» y, si es el buscado, «Buscado».
  function priceItem(price) {
    const item = document.createElement('li');
    item.className = price.searched ? 'detail-price-row searched' : 'detail-price-row';
    const name = document.createElement('span');
    name.className = 'fuel-name';
    name.textContent = price.name;
    const value = document.createElement('span');
    value.className = 'fuel-price';
    value.textContent = formatPrice(price.price, price.unit);
    item.append(name, ' · ', value);
    if (price.searched) {
      const tag = document.createElement('span');
      tag.className = 'searched-tag';
      tag.textContent = 'Buscado';
      item.append(' ', tag);
    }
    return item;
  }

  function setExpanded(expanded) {
    panel.classList.toggle('expanded', expanded);
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.textContent = expanded ? 'Ocultar lista' : 'Ver lista';
  }
  toggle.addEventListener('click', () => setExpanded(!panel.classList.contains('expanded')));

  return {
    elements: {fuel: $('fuel'), radius: $('radius'), back: $('back-to-location'),
      status: $('status'), map: $('map'), retry, toggle, cheapest, panel, detail},

    isDesktop() {
      return DESKTOP.matches;
    },

    // Alto de lo que tapa el mapa por abajo en el móvil (la hoja a la vista).
    sheetCover() {
      if (DESKTOP.matches) return 0;
      const sheet = detail.hidden ? panel : detail;
      const top = sheet.getBoundingClientRect().top;
      return Math.max(0, window.innerHeight - top);
    },

    listVisible() {
      return DESKTOP.matches || panel.classList.contains('expanded');
    },

    setHint(text) {
      if (text) show($('hint'), text);
      else hide($('hint'));
    },

    // Mensaje de error o de estado; con `retryAfter` segundos, «Reintentar»
    // queda desactivado hasta que pasan.
    showMessage(text, {retryable = true, retryAfter = 0} = {}) {
      show($('message'), text);
      clearTimeout(retryTimer);
      retry.hidden = !retryable;
      retry.disabled = retryAfter > 0;
      if (retryAfter > 0) {
        retryTimer = setTimeout(() => {
          retry.disabled = false;
        }, retryAfter * 1000);
      }
    },

    clearMessage() {
      hide($('message'));
      clearTimeout(retryTimer);
      retry.hidden = true;
      retry.disabled = false;
    },

    showStale(text) {
      show($('stale'), text);
    },

    // Sin lista que mostrar: fuera recuento, más barata, «Ver lista» y cuerpo;
    // la hoja se pliega (spec, «Se pliega al quedarse sin lista»).
    clearResults({fold = false} = {}) {
      list.replaceChildren();
      for (const id of ['count', 'more', 'discarded', 'capture']) hide($(id));
      $('legend').hidden = true;
      cheapest.hidden = true;
      cheapest.textContent = '';
      toggle.hidden = true;
      if (fold) setExpanded(false);
    },

    showSummary({count, more, discarded, capture, cheapestText}) {
      show($('count'), count);
      if (more) show($('more'), more);
      else hide($('more'));
      if (discarded) show($('discarded'), discarded);
      else hide($('discarded'));
      show($('capture'), capture);
      cheapest.textContent = `Más barata: ${cheapestText}`;
      cheapest.hidden = false;
      toggle.hidden = false;
      setExpanded(panel.classList.contains('expanded'));
    },

    showLegend({count, tiers, min, max, unit}) {
      const single = tiers.every((t) => t === 'single');
      $('legend-tiers').hidden = single;
      if (single) {
        hide($('legend-explain'));
        show($('legend-range'), `Todas a ${formatPrice(min, unit)}`);
      } else {
        show($('legend-explain'), `Colores por tercios de las ${count} gasolineras mostradas; `
          + 'el precio mínimo y el máximo siempre en sus extremos');
        show($('legend-range'), `De ${formatPriceShort(min)} a ${formatPrice(max, unit)}`);
      }
      $('legend').hidden = false;
    },

    renderStations(stations, tiers, unit) {
      const rows = stations.map((station, index) => {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `station-row tier-${tiers[index]}`;
        button.dataset.id = String(station.id);
        const parts = [
          ['brand', station.brand || 'Sin rótulo'],
          ['sep', ' · '],
          ['dist', formatDistance(station.distance_km)],
          ['sep', ' · '],
          ['price', formatPrice(station.price, unit)],
        ];
        for (const [name, text] of parts) {
          const span = document.createElement('span');
          span.className = name;
          span.textContent = text;
          button.append(span);
        }
        item.append(button);
        return item;
      });
      list.replaceChildren(...rows);
    },

    row(id) {
      return list.querySelector(`.station-row[data-id="${CSS.escape(String(id))}"]`);
    },

    highlight(id, {scroll = false} = {}) {
      for (const row of list.querySelectorAll('.station-row.selected')) {
        row.classList.remove('selected');
        row.removeAttribute('aria-current');
      }
      if (id === null) return;
      const row = this.row(id);
      if (!row) return;
      row.classList.add('selected');
      row.setAttribute('aria-current', 'true');
      if (scroll && DESKTOP.matches) row.scrollIntoView({block: 'nearest'});
    },

    // Datos de la búsqueda en la ficha: hoja inferior en el móvil, en el panel
    // en escritorio. Solo se reemplaza `#detail-head` (add-station-detail, D8).
    openDetail(station, unit) {
      const lines = [
        ['h2', 'detail-brand', station.brand || 'Sin rótulo'],
        ['p', 'detail-address', station.address || 'Dirección no disponible'],
        ['p', 'detail-municipality', station.municipality || 'Municipio no disponible'],
        ['p', 'detail-price', formatPrice(station.price, unit)],
        ['p', 'detail-distance', formatDistance(station.distance_km)],
      ];
      const elements = lines.map(([tag, name, text]) => {
        const element = document.createElement(tag);
        element.className = name;
        element.textContent = text;
        return element;
      });
      $('detail-head').replaceChildren(...elements);
      detail.hidden = false;
      document.body.classList.add('detail-open');
      $('detail-close').focus({preventScroll: true});
    },

    closeDetail() {
      cancelDetailTimers();
      detail.hidden = true;
      document.body.classList.remove('detail-open');
      $('detail-head').replaceChildren();
      detailStatus.textContent = '';
      detailRetry.hidden = true;
      $('detail-info').hidden = true;
      $('detail-schedule').replaceChildren();
      $('detail-prices').replaceChildren();
    },

    setDirections({href, label}) {
      directions.href = href;
      directions.setAttribute('aria-label', label);
    },

    // Estado del detalle (D8): la zona de estado solo lleva un texto corto, que
    // se pone en el siguiente frame para que los lectores lo anuncien aunque la
    // ficha acabe de mostrarse; horario y precios van fuera de esa zona.
    // `onPainted` se llama tras ese frame, cuando la ficha ya tiene su alto.
    renderDetail(entry, {newer = null, onPainted = () => {}} = {}) {
      cancelDetailTimers();
      let text;
      if (entry.status === 'loading') text = 'Cargando horario…';
      else if (entry.status === 'ok') text = 'Ficha cargada';
      else text = errorText(entry.result);
      statusFrame = requestAnimationFrame(() => {
        detailStatus.textContent = text;
        onPainted();
      });

      const retryable = entry.status === 'error' && entry.retryable;
      detailRetry.hidden = !retryable;
      const wait = retryable ? entry.retryAt - Date.now() : 0;
      detailRetry.disabled = wait > 0;
      if (wait > 0) {
        detailRetryTimer = setTimeout(() => {
          detailRetry.disabled = false;
        }, wait);
      }

      const info = $('detail-info');
      if (entry.status !== 'ok') {
        info.hidden = true;
        $('detail-schedule').replaceChildren();
        $('detail-prices').replaceChildren();
        return;
      }
      const {lines, prices} = entry.result;
      if (newer) show($('detail-newer'), newer);
      else hide($('detail-newer'));
      $('detail-schedule').replaceChildren(...lines.map((line) => listItem('schedule-line', line)));
      $('detail-no-schedule').hidden = lines.length > 0;
      $('detail-prices').replaceChildren(...prices.map(priceItem));
      $('detail-no-prices').hidden = prices.length > 0;
      info.hidden = false;
    },

    focusDetailStatus() {
      detailStatus.focus({preventScroll: true});
    },

    detailOpen() {
      return !detail.hidden;
    },
  };
}
