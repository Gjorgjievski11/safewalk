import { MOCK_REPORTS } from './mock.js';

export const USE_MOCK = true;   // flip to false when the backend is up

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