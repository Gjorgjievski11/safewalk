import { USE_MOCK } from './api.js';

const $ = (id) => document.getElementById(id);
const isDesktop = () => window.matchMedia('(min-width: 640px)').matches;

function groupLocal(pins) {
  const by = new Map();
  for (const r of pins) {
    const street = (r.street ?? '').trim();
    if (!street) continue;
    const g = by.get(street) ?? { street, count: 0, labels: {} };
    g.count++;
    g.labels[r.label] = (g.labels[r.label] ?? 0) + 1;
    by.set(street, g);
  }
  return [...by.values()].sort((a, b) => b.count - a.count);
}

// server labels may be {label: n} or ["label", ...]
function normalize(row) {
  let labels = row.labels ?? {};
  if (Array.isArray(labels)) {
    labels = labels.reduce((acc, l) => { acc[l] = (acc[l] ?? 0) + 1; return acc; }, {});
  }
  return { ...row, labels };
}

// spreadsheets run text starting with = + - @ as a formula, so defuse it
function csvCell(v, guard = false) {
  let s = String(v ?? '');
  if (guard && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

function downloadCsvLocal(pins) {
  const head = 'id,label,street,lat,lon,report_text';
  const lines = pins.map((r) => [
    csvCell(r.id),
    csvCell(r.label),
    csvCell(r.street, true),
    csvCell(r.lat),
    csvCell(r.lon),
    csvCell(r.report_text, true),
  ].join(','));
  // BOM so Excel reads the Cyrillic correctly
  const blob = new Blob(['\ufeff' + [head, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'safewalk-reports.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function initHotspots({ map, api, getPins, labels }) {
  let open = false;

  function setOpen(v) {
    open = v;
    $('hotPanel').hidden = !v;
    $('hotspotsBtn').hidden = v;
    $('routeBtn').hidden = v;
    $('fab').hidden = v;
    $('legend').classList.toggle('hidden', v);
  }

  function flyTo(row) {
    let pts = getPins()
      .filter((r) => (r.street ?? '').trim() === row.street)
      .map((r) => [r.lat, r.lon]);
    if (!pts.length && row.lat != null && row.lon != null) pts = [[row.lat, row.lon]];
    if (!pts.length) return;
    if (pts.length === 1) {
      map.flyTo(pts[0], 17);
    } else {
      map.flyToBounds(L.latLngBounds(pts), {
        maxZoom: 17,
        paddingTopLeft: [40, 80],
        paddingBottomRight: [40, isDesktop() ? 40 : 80],
      });
    }
    if (!isDesktop()) setOpen(false);   // phone: get the panel out of the way
  }

  function render(rows) {
    const list = $('hotList');
    list.replaceChildren();
    $('hotEmpty').hidden = rows.length > 0;

    rows.slice(0, 5).forEach((row, i) => {
      const btn = document.createElement('button');
      btn.className = 'flex w-full items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3 text-left';

      const rank = document.createElement('span');
      rank.className = 'flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white';
      rank.textContent = String(i + 1);

      const body = document.createElement('div');
      body.className = 'min-w-0 flex-1';
      const name = document.createElement('div');
      name.className = 'truncate font-semibold';
      name.textContent = row.street;
      const chips = document.createElement('div');
      chips.className = 'mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600';
      for (const [key, n] of Object.entries(row.labels)) {
        const chip = document.createElement('span');
        chip.className = 'flex items-center gap-1';
        const dot = document.createElement('span');
        dot.className = 'inline-block h-2.5 w-2.5 shrink-0 rounded-full';
        dot.style.background = (labels[key] ?? labels.none).color;
        const txt = document.createElement('span');
        txt.textContent = `${(labels[key] ?? labels.none).name} ×${n}`;
        chip.append(dot, txt);
        chips.appendChild(chip);
      }
      body.append(name, chips);

      const count = document.createElement('span');
      count.className = 'text-lg font-bold';
      count.textContent = String(row.count);

      btn.append(rank, body, count);
      btn.addEventListener('click', () => flyTo(row));
      list.appendChild(btn);
    });
  }

  async function openPanel() {
    setOpen(true);
    render(groupLocal(getPins()));   // instant, local
    try {
      const server = await api.getHotspots();
      if (open && Array.isArray(server) && server.length) {
        render(server.map(normalize).sort((a, b) => b.count - a.count));
      }
    } catch (e) {
      console.error(e);   // keep the local ranking
    }
  }

  $('hotspotsBtn').addEventListener('click', openPanel);
  $('hotClose').addEventListener('click', () => setOpen(false));
  $('csvBtn').addEventListener('click', () => {
    if (USE_MOCK) return downloadCsvLocal(getPins());
    const a = document.createElement('a');
    a.href = '/export.csv';
    a.download = 'safewalk-reports.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}