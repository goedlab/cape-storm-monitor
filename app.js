'use strict';

// ── i18n ──────────────────────────────────────────────────────────────────────

const TRANSLATIONS = {
  en: {
    'section.incidents': 'Active Incidents',
    'section.timeline':  'Updates Timeline',
    'section.shelters':  'Open Shelters',
    'stats.incidents':   'Active Incidents',
    'stats.areas':       'Areas Affected',
    'stats.roads':       'Roads Closed',
    'stats.shelters':    'Shelters Open',
    'shelter.bring':     'Bring:',
    'status.ALL_CLEAR':  'ALL CLEAR',
    'status.WATCH':      'WATCH',
    'status.WARNING':    'WARNING',
    'status.EMERGENCY':  'EMERGENCY',
  },
  af: {
    'section.incidents': 'Aktiewe Voorvalle',
    'section.timeline':  'Opdaterings Tydlyn',
    'section.shelters':  'Oop Skuilings',
    'stats.incidents':   'Aktiewe Voorvalle',
    'stats.areas':       'Gebiede Geraak',
    'stats.roads':       'Paaie Gesluit',
    'stats.shelters':    'Skuilings Oop',
    'status.ALL_CLEAR':  'ALLES VEILIG',
    'status.WATCH':      'WAAK',
    'status.WARNING':    'WAARSKUWING',
    'status.EMERGENCY':  'NOODGEVAL',
  },
  xh: {
    'section.incidents': 'Iziganeko Ezisebenzayo',
    'section.timeline':  'Uluhlu Lweenkcukacha',
    'section.shelters':  'Iindawo Zokuphepha Ezivulekileyo',
    'stats.incidents':   'Iziganeko Ezisebenzayo',
    'stats.areas':       'Iindawo Ezichatshazelweyo',
    'stats.roads':       'Iindlela Ezivaliweyo',
    'stats.shelters':    'Iindawo Zokuphepha Ezivulekileyo',
    'status.ALL_CLEAR':  'KUKHUSELEKILE',
    'status.WATCH':      'QAPHELA',
    'status.WARNING':    'ISILUMKISO',
    'status.EMERGENCY':  'INGXAKI EBULALAYO',
  },
};

let currentLang = localStorage.getItem('cst-lang') || 'en';

function t(key) {
  return (TRANSLATIONS[currentLang] || TRANSLATIONS.en)[key]
      || TRANSLATIONS.en[key]
      || key;
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.documentElement.lang = currentLang;
}

function setLang(lang) {
  if (!TRANSLATIONS[lang]) return;
  currentLang = lang;
  localStorage.setItem('cst-lang', lang);
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
  applyTranslations();
  // Re-render status level text if data is already loaded
  const levelEl = document.getElementById('status-level');
  if (levelEl && levelEl.dataset.status) {
    levelEl.textContent = t(`status.${levelEl.dataset.status}`);
  }
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SEVERITY_COLORS = {
  ALL_CLEAR: '#859900',
  WATCH:     '#b58900',
  WARNING:   '#cb4b16',
  EMERGENCY: 'rgb(252,61,33)'
};

const TYPE_ICONS = {
  coastal:        '🌊',
  storm:          '⛈️',
  flood:          '💧',
  fire:           '🔥',
  wind:           '💨',
  road:           '🚧',
  power:          '⚡',
  internet:       '📡',
  infrastructure: '🔧',
  shelter:        '➕',
  default:        '⚠️'
};

let currentLastUpdated = null;
let lastData = null;
let map = null;
let incidentLayer = null;
let shelterLayer = null;

// ── Map ──────────────────────────────────────────────────────────────────────

function initMap() {
  map = L.map('map', { zoomControl: true }).setView([-33.9249, 18.4241], 10);

  L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Tiles &copy; <a href="https://hot.openstreetmap.org/">Humanitarian OpenStreetMap Team</a>',
    subdomains: 'abc',
    maxZoom: 19
  }).addTo(map);

  incidentLayer = L.layerGroup().addTo(map);
  shelterLayer  = L.layerGroup().addTo(map);

  L.control.layers(null, {
    'Active Incidents': incidentLayer,
    'Shelters':         shelterLayer
  }, { collapsed: false, position: 'topright' }).addTo(map);

  addLegend();

  window.addEventListener('resize', () => map.invalidateSize());
}

function initMapTabs() {
  document.querySelectorAll('.map-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.map-tab').forEach(t => t.classList.toggle('active', t === tab));
      document.querySelectorAll('.map-panel').forEach(p => {
        p.classList.toggle('active', p.id === `map-panel-${target}`);
      });
      if (target === 'incidents') {
        if (!map) {
          initMap();
          if (lastData) updateMapMarkers(lastData.incidents, lastData.map_markers);
        } else {
          setTimeout(() => map.invalidateSize(), 50);
        }
      }
    });
  });
}

function addLegend() {
  const legend = L.control({ position: 'bottomleft' });
  legend.onAdd = function () {
    const div = L.DomUtil.create('div', 'map-legend');
    div.innerHTML = `
      <div class="legend-title">Severity</div>
      <div class="legend-row"><span class="legend-dot" style="background:rgb(252,61,33);"></span> Emergency</div>
      <div class="legend-row"><span class="legend-dot" style="background:#cb4b16;"></span> Warning</div>
      <div class="legend-row"><span class="legend-dot" style="background:#b58900;"></span> Watch</div>
      <div class="legend-row"><span class="legend-dot" style="background:#859900;"></span> All Clear / Shelter</div>
    `;
    return div;
  };
  legend.addTo(map);
}

function makeMarkerIcon(type, severity) {
  const emoji = TYPE_ICONS[type] || TYPE_ICONS.default;
  const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.WATCH;
  return L.divIcon({
    html: `<div class="map-marker" style="background:${color};">${emoji}</div>`,
    className: '',
    iconSize:   [36, 36],
    iconAnchor: [18, 36],
    popupAnchor: [0, -38]
  });
}

function updateMapMarkers(incidents, mapMarkers) {
  if (!incidentLayer || !shelterLayer) return;

  incidentLayer.clearLayers();
  shelterLayer.clearLayers();

  incidents
    .filter(inc => inc.active && inc.lat != null && inc.lng != null)
    .forEach(inc => {
      const icon   = makeMarkerIcon(inc.type, inc.severity);
      const marker = L.marker([inc.lat, inc.lng], { icon });
      marker.bindPopup(buildPopupHtml(inc));
      incidentLayer.addLayer(marker);
    });

  if (mapMarkers) {
    mapMarkers
      .filter(m => m.type === 'shelter')
      .forEach(m => {
        const icon   = makeMarkerIcon('shelter', m.severity || 'ALL_CLEAR');
        const marker = L.marker([m.lat, m.lng], { icon });
        marker.bindPopup(`<div class="popup-content"><strong class="popup-title">${m.label}</strong></div>`);
        shelterLayer.addLayer(marker);
      });
  }
}

function buildPopupHtml(inc) {
  const time = formatDateTime(inc.updated);
  const sourceHtml = inc.source_url
    ? `<a href="${inc.source_url}" target="_blank" rel="noopener" class="popup-source">${inc.source}</a>`
    : `<span class="popup-source">${inc.source || ''}</span>`;
  return `
    <div class="popup-content">
      <div class="popup-header">
        <span class="popup-type">${inc.type.toUpperCase()}</span>
        <span class="severity-badge ${inc.severity}">${inc.severity.replace('_', ' ')}</span>
      </div>
      <strong class="popup-title">${inc.title}</strong>
      <p class="popup-area">${inc.area}</p>
      <p class="popup-desc">${inc.description}</p>
      <div class="popup-footer">
        <span class="popup-updated">Updated ${time}</span>
        ${sourceHtml}
      </div>
    </div>
  `;
}

// ── Status banner ─────────────────────────────────────────────────────────────

function updateStatusBanner(status, lastUpdated, summary) {
  const banner  = document.getElementById('status-banner');
  const levelEl = document.getElementById('status-level');
  const summaryEl = document.getElementById('status-summary');
  const updatedEl = document.getElementById('status-updated');

  banner.className      = `status-banner ${status}`;
  levelEl.textContent   = t(`status.${status}`);
  levelEl.dataset.status = status;
  summaryEl.textContent = summary || '';
  updatedEl.textContent = `Last updated ${formatDateTime(lastUpdated)} SAST`;

  document.title = `[${t(`status.${status}`)}] Cape Storm Monitor`;
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function updateStatsBar(stats) {
  document.getElementById('stat-incidents').textContent = stats.active_incidents ?? '—';
  document.getElementById('stat-areas').textContent     = stats.areas_affected   ?? '—';
  document.getElementById('stat-roads').textContent     = stats.roads_closed     ?? '—';
  document.getElementById('stat-shelters').textContent  = stats.shelters_open    ?? '—';
}

// ── Incident cards ────────────────────────────────────────────────────────────

const SEVERITY_ORDER = { EMERGENCY: 0, WARNING: 1, WATCH: 2, ALL_CLEAR: 3 };

function updateIncidentCards(incidents) {
  const list   = document.getElementById('incident-list');
  const active = incidents
    .filter(i => i.active)
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));

  if (active.length === 0) {
    list.innerHTML = '<p class="empty-state">No active incidents.</p>';
    return;
  }

  const prevFilter = document.getElementById('incident-filter')?.value || '';

  const rows = active.map(inc => {
    const time      = formatDateTime(inc.updated);
    const hasDetail = !!(inc.description || inc.actions?.length || inc.alternate_route);
    return `
      <tr class="incident-row severity-row-${inc.severity}${hasDetail ? ' expandable' : ''}"
          data-search="${(inc.title + ' ' + inc.area).toLowerCase()}"
          ${hasDetail ? `onclick="toggleIncidentDetail('${inc.id}')"` : ''}>
        <td class="incident-name-cell">
          ${hasDetail ? '<span class="expand-hint">&#9658;</span>' : ''}
          <span class="incident-name-text">${inc.title}</span>
        </td>
        <td class="incident-area-cell">${inc.area}</td>
        <td class="incident-time-cell">${time}</td>
        <td class="incident-severity-cell">
          <span class="severity-badge ${inc.severity}">${inc.severity.replace('_', ' ')}</span>
        </td>
      </tr>
      ${hasDetail ? `<tr class="incident-detail-row" id="detail-${inc.id}">
        <td colspan="4">${buildIncidentDetail(inc)}</td>
      </tr>` : ''}
    `;
  }).join('');

  list.innerHTML = `
    <div class="incident-filter-wrap">
      <input class="incident-filter" id="incident-filter" type="search"
             placeholder="Filter by area or incident…"
             value="${prevFilter}" autocomplete="off" />
    </div>
    <table class="incident-table">
      <thead>
        <tr>
          <th>Incident</th>
          <th class="col-area">Area</th>
          <th class="col-time">Updated</th>
          <th>Severity</th>
        </tr>
      </thead>
      <tbody id="incident-tbody">${rows}</tbody>
    </table>
  `;

  document.getElementById('incident-filter').addEventListener('input', filterIncidents);
  if (prevFilter) filterIncidents();
}

function buildIncidentDetail(inc) {
  const parts = [];
  if (inc.description) {
    parts.push(`<p class="detail-description">${inc.description}</p>`);
  }
  if (inc.alternate_route) {
    parts.push(`<div class="detail-alternate"><span class="detail-label">Alternate route</span>${inc.alternate_route}</div>`);
  }
  if (inc.actions?.length) {
    const items = inc.actions.map(a =>
      `<div class="detail-action"><span class="detail-arrow">&#8594;</span>${a}</div>`
    ).join('');
    parts.push(`<div class="detail-actions">${items}</div>`);
  }
  if (inc.source) {
    const srcHtml = inc.source_url
      ? `<a href="${inc.source_url}" target="_blank" rel="noopener">${inc.source}</a>`
      : inc.source;
    parts.push(`<div class="detail-source">${srcHtml}</div>`);
  }
  return `<div class="incident-detail-body">${parts.join('')}</div>`;
}

function toggleIncidentDetail(id) {
  const detail = document.getElementById(`detail-${id}`);
  if (!detail) return;
  const open = detail.classList.toggle('open');
  const row  = detail.previousElementSibling;
  if (row) {
    const hint = row.querySelector('.expand-hint');
    if (hint) hint.innerHTML = open ? '&#9660;' : '&#9658;';
  }
}

function filterIncidents() {
  const query = (document.getElementById('incident-filter')?.value || '').toLowerCase();
  document.querySelectorAll('#incident-tbody .incident-row').forEach(row => {
    const match = !query || (row.dataset.search || '').includes(query);
    row.style.display = match ? '' : 'none';
    const detail = row.nextElementSibling;
    if (detail?.classList.contains('incident-detail-row')) {
      if (!match) detail.classList.remove('open');
      detail.style.display = match ? '' : 'none';
    }
  });
}

// ── Shelters ──────────────────────────────────────────────────────────────────

function updateShelters(shelters) {
  const section = document.getElementById('shelters-section');
  if (!section) return;
  const open = (shelters || []).filter(s => s.open);
  section.style.display = open.length ? '' : 'none';
  if (!open.length) return;

  document.getElementById('shelters-list').innerHTML = open.map(s => `
    <div class="shelter-card">
      <div class="shelter-header">
        <span class="shelter-open-dot"></span>
        <strong class="shelter-name">${s.name}</strong>
      </div>
      <div class="shelter-address">${s.address}</div>
      ${s.contact ? `<a href="tel:${s.contact.replace(/\s/g, '')}" class="shelter-contact">${s.contact}</a>` : ''}
      ${s.bring?.length ? `<div class="shelter-bring"><span class="shelter-bring-label">Bring: </span>${s.bring.join(' · ')}</div>` : ''}
    </div>
  `).join('');
}

// ── Timeline ──────────────────────────────────────────────────────────────────

function updateTimeline(timeline) {
  const list = document.getElementById('timeline-list');
  if (!timeline || timeline.length === 0) {
    list.innerHTML = '<p class="empty-state">No recent updates.</p>';
    return;
  }

  const sorted = [...timeline].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  list.innerHTML = sorted.map(item => {
    const time = formatDateTime(item.timestamp);
    const linkHtml = item.url
      ? `<a href="${item.url}" target="_blank" rel="noopener" class="timeline-link">&#8599;</a>`
      : '';
    return `
      <div class="timeline-item">
        <span class="timeline-time">${time}</span>
        <span class="timeline-dot ${item.severity}"></span>
        <div class="timeline-body">
          <div class="timeline-source">${item.source}</div>
          <div class="timeline-text">${item.text}${linkHtml}</div>
        </div>
      </div>
    `;
  }).join('');
}

// ── Stale warning ─────────────────────────────────────────────────────────────

function showStaleWarning() {
  document.getElementById('stale-warning').classList.add('visible');
}
function hideStaleWarning() {
  document.getElementById('stale-warning').classList.remove('visible');
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString('en-ZA', {
      hour: '2-digit', minute: '2-digit',
      timeZone: 'Africa/Johannesburg'
    });
  } catch { return iso; }
}

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-ZA', {
      day: 'numeric', month: 'short',
      hour: '2-digit', minute: '2-digit',
      timeZone: 'Africa/Johannesburg'
    });
  } catch { return iso; }
}

// ── Poll ──────────────────────────────────────────────────────────────────────

async function pollUpdates() {
  try {
    const res = await fetch('data/data.json?t=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.last_updated !== currentLastUpdated) {
      currentLastUpdated = data.last_updated;
      lastData = data;
      updateStatusBanner(data.status, data.last_updated, data.summary);
      updateStatsBar(data.stats);
      updateIncidentCards(data.incidents);
      updateMapMarkers(data.incidents, data.map_markers);
      updateTimeline(data.timeline);
      updateShelters(data.shelters);
    }

    hideStaleWarning();
  } catch (err) {
    console.error('Cape Storm Monitor: data fetch failed —', err.message);
    showStaleWarning();
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Lang toggle
  document.getElementById('lang-toggle').addEventListener('click', e => {
    const btn = e.target.closest('.lang-btn');
    if (btn) setLang(btn.dataset.lang);
  });
  // Restore saved language
  setLang(currentLang);

  initMapTabs();
  initMap();
  pollUpdates();
  setInterval(pollUpdates, 2 * 60 * 1000);
});
