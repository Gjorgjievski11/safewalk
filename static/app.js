import * as api from './api.js';
import { initRoute } from './route.js';
import { initHotspots } from './hotspots.js';

const LABELS = {
  parked_on_sidewalk: { color: '#ef4444', name: 'Parked on sidewalk' },
  overgrown:          { color: '#22c55e', name: 'Overgrown path' },
  dark_street:        { color: '#8b5cf6', name: 'Dark street' },
  broken_light:       { color: '#f97316', name: 'Broken streetlight' },
  none:               { color: '#9ca3af', name: 'Other' },
};
const PICKABLE = ['parked_on_sidewalk', 'overgrown', 'dark_street', 'broken_light'];

const $ = (id) => document.getElementById(id);

/* ---------- map ---------- */
const map = L.map('map').setView([41.9981, 21.4254], 14);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);
map.attributionControl.setPosition('bottomleft');
const pins = L.layerGroup().addTo(map);

let reports = [];

function popupFor(r) {
  const el = document.createElement('div');
  el.className = 'w-52 max-w-[60vw] text-sm';
  if (r.photo_url) {
    const img = document.createElement('img');
    img.src = r.photo_url;
    img.className = 'mb-2 w-full rounded-md';
    el.appendChild(img);
  }
  const title = document.createElement('div');
  title.className = 'font-semibold';
  title.textContent = (LABELS[r.label] ?? LABELS.none).name;
  const street = document.createElement('div');
  street.className = 'text-gray-500';
  street.textContent = r.street ?? '';
  const text = document.createElement('p');
  text.className = 'mt-1';
  text.textContent = r.report_text ?? '';
  el.append(title, street, text);
  return el;
}

function addPin(r) {
  const style = LABELS[r.label] ?? LABELS.none;
  return L.circleMarker([r.lat, r.lon], {
    radius: 10, color: '#fff', weight: 2,
    fillColor: style.color, fillOpacity: 0.95,
    bubblingMouseEvents: false,
  }).bindPopup(popupFor(r)).addTo(pins);
}

async function load() {
  try {
    reports = await api.getReports();
    pins.clearLayers();
    reports.forEach(addPin);
  } catch (e) {
    console.error(e);
  }
}

function buildLegend() {
  for (const { color, name } of Object.values(LABELS)) {
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2 whitespace-nowrap leading-snug';
    const dot = document.createElement('span');
    dot.className = 'inline-block h-3 w-3 shrink-0 rounded-full';
    dot.style.background = color;
    const label = document.createElement('span');
    label.textContent = name;
    row.append(dot, label);
    $('legend-rows').appendChild(row);
  }
  if (window.matchMedia('(min-width: 640px)').matches) $('legend').open = true;
}

/* ---------- report flow ---------- */
let sheetOpen = false;
let busy = false;
let file = null;
let photoId = null;
let latlng = null;
let pending = null;
let lastText = '';

const pinIcon = L.divIcon({
  className: 'rounded-full border-[3px] border-white bg-blue-600 shadow-[0_0_0_2px_#2563eb,0_2px_6px_rgba(0,0,0,0.4)]',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function buildSelect() {
  const sel = $('label');
  sel.appendChild(new Option('Choose a category…', ''));
  for (const key of PICKABLE) sel.appendChild(new Option(LABELS[key].name, key));
}

function setStatus(msg, warn = false) {
  const s = $('status');
  s.textContent = msg;
  s.classList.toggle('text-amber-700', warn);
  s.classList.toggle('text-gray-700', !warn);
}

function updateSubmit() {
  $('submit').disabled = busy || !(file && $('label').value && latlng);
}

function updateLocText() {
  $('loc-text').textContent = latlng
    ? `Pin at ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)} (drag to adjust)`
    : 'Tap the map to place the pin';
}

function setLoc(ll) {
  latlng = ll;
  if (!pending) {
    pending = L.marker(ll, { icon: pinIcon, draggable: true }).addTo(map);
    pending.on('dragend', () => { latlng = pending.getLatLng(); updateLocText(); });
  } else {
    pending.setLatLng(ll);
  }
  updateLocText();
  updateSubmit();
}

function openSheet() {
  sheetOpen = true;
  $('sheet').hidden = false;
  $('fab').hidden = true;
  $('routeBtn').hidden = true;
  $('hotspotsBtn').hidden = true;
  $('legend').classList.add('hidden');
}

function resetFlow() {
  sheetOpen = false;
  busy = false;
  file = null;
  photoId = null;
  latlng = null;
  if (pending) { map.removeLayer(pending); pending = null; }
  $('file').value = '';
  $('preview').hidden = true;
  $('label').value = '';
  $('label').hidden = true;
  setStatus('');
  updateLocText();
  $('form').hidden = false;
  $('result').hidden = true;
  $('copy').textContent = 'Copy text';
  $('sheet').hidden = true;
  $('fab').hidden = false;
  $('routeBtn').hidden = false;
  $('hotspotsBtn').hidden = false;
  $('legend').classList.remove('hidden');
  updateSubmit();
}

$('fab').addEventListener('click', openSheet);
$('close').addEventListener('click', resetFlow);
$('done').addEventListener('click', resetFlow);

map.on('click', (e) => { if (sheetOpen && !busy) setLoc(e.latlng); });

$('file').addEventListener('change', async () => {
  const f = $('file').files[0];
  if (!f) return;
  file = f;
  photoId = null;
  $('preview').src = URL.createObjectURL(f);
  $('preview').hidden = false;
  $('label').hidden = false;
  $('label').value = '';
  setStatus('Analyzing photo…');
  updateSubmit();

  try {
    const r = await api.classify(f);
    photoId = r.photo_id ?? null;
    if (PICKABLE.includes(r.label) && r.confidence >= 0.5) {
      $('label').value = r.label;
      setStatus(`Looks like: ${LABELS[r.label].name} (${Math.round(r.confidence * 100)}%). Change it if wrong.`);
    } else {
      setStatus('Not sure what this is. Please pick a category.', true);
    }
  } catch (e) {
    console.error(e);
    setStatus("Couldn't analyze the photo. Please pick a category.", true);
  }
  updateSubmit();
});

$('label').addEventListener('change', updateSubmit);

$('geo').addEventListener('click', () => {
  if (!navigator.geolocation) return setStatus('Location not available. Tap the map.', true);
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
      map.setView(ll, 17);
      setLoc(ll);
    },
    () => setStatus('Location unavailable here. Tap the map instead.', true),
    { enableHighAccuracy: true, timeout: 8000 },
  );
});

$('submit').addEventListener('click', async () => {
  busy = true;
  updateSubmit();
  setStatus('Saving…');
  try {
    const report = await api.postReport(
      { label: $('label').value, lat: latlng.lat, lon: latlng.lng, photo_id: photoId },
      file,
    );
    if (pending) { map.removeLayer(pending); pending = null; }
    const marker = addPin(report);
    reports.push(report);
    map.flyTo([report.lat, report.lon], Math.max(map.getZoom(), 16));
    marker.openPopup();

    lastText = report.report_text ?? '';
    $('result-text').textContent = lastText;
    $('form').hidden = true;
    $('result').hidden = false;
  } catch (e) {
    console.error(e);
    setStatus('Could not save the report. Try again.', true);
  } finally {
    busy = false;
    updateSubmit();
  }
});

$('copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(lastText);
    $('copy').textContent = 'Copied';
  } catch {
    $('copy').textContent = 'Copy failed';
  }
});

buildLegend();
buildSelect();
load();
initRoute({ map, api, getPins: () => reports });
initHotspots({ map, api, getPins: () => reports, labels: LABELS });