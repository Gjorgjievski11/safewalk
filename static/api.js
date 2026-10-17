import { MOCK_REPORTS } from './mock.js';

export const USE_MOCK = true;

const MOCK_LABELS = ['parked_on_sidewalk', 'overgrown', 'dark_street', 'broken_light'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function getReports() {
  if (USE_MOCK) return MOCK_REPORTS;
  const res = await fetch('/reports');
  if (!res.ok) throw new Error(`GET /reports ${res.status}`);
  return res.json();
}

// -> { label, confidence, brightness, photo_id? }
export async function classify(file) {
  if (USE_MOCK) {
    await sleep(700);
    return {
      label: MOCK_LABELS[Math.floor(Math.random() * MOCK_LABELS.length)],
      confidence: 0.3 + Math.random() * 0.65,
      brightness: 100,
      photo_id: null,
    };
  }
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/classify', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`POST /classify ${res.status}`);
  return res.json();
}

// report: { label, lat, lon, photo_id } -> full report object for the pin
export async function postReport(report, file) {
  if (USE_MOCK) {
    await sleep(500);
    const full = {
      id: Date.now(),
      ...report,
      street: 'New report',
      photo_url: URL.createObjectURL(file),
      report_text: `Пријава: ${report.label} на локација ${report.lat.toFixed(4)}, ${report.lon.toFixed(4)}.`,
    };
    MOCK_REPORTS.push(full);
    return full;
  }
  const res = await fetch('/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(report),
  });
  if (!res.ok) throw new Error(`POST /reports ${res.status}`);
  const data = await res.json();   // { id, report_text, photo_url? }
  return { ...report, street: '', photo_url: URL.createObjectURL(file), ...data };
}

// from, to: L.LatLng -> { direct: {coords: [[lat,lon],...], length?}, safer: {...}, demo? }
export async function getRoute(from, to) {
  if (USE_MOCK) {
    await sleep(600);
    return { ...mockRoute(from, to), demo: true };
  }
  const res = await fetch(`/route?from=${from.lat},${from.lng}&to=${to.lat},${to.lng}`);
  if (!res.ok) throw new Error(`GET /route ${res.status}`);
  return res.json();
}

// Kept for offline UI development; production routing always uses the backend.
export function mockRoute(from, to) {
  const N = 12;
  const dy = to.lat - from.lat;
  const dx = to.lng - from.lng;
  const direct = [];
  const safer = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const lat = from.lat + dy * t;
    const lon = from.lng + dx * t;
    direct.push([lat, lon]);
    const bulge = Math.sin(Math.PI * t) * 0.18;
    safer.push([lat + dx * bulge, lon - dy * bulge]);
  }
  return { direct: { coords: direct }, safer: { coords: safer } };
}

// -> [{street, count, labels}] from the server, or null in mock mode
// (hotspots.js then ranks the pins locally)
export async function getHotspots() {
  if (USE_MOCK) return null;
  const res = await fetch('/hotspots');
  if (!res.ok) throw new Error(`GET /hotspots ${res.status}`);
  return res.json();
}
