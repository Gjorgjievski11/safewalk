const $ = (id) => document.getElementById(id);

const PROBLEM_RADIUS = 20; // meters
const fmt = (m) => (m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`);
const plural = (n) => `${n} ${n === 1 ? 'problem' : 'problems'}`;

// distance in meters from point p to segment a-b, all [lat, lon]
function distToSegM(p, a, b) {
  const kx = 111320 * Math.cos((p[0] * Math.PI) / 180);
  const ky = 110540;
  const px = (p[1] - a[1]) * kx, py = (p[0] - a[0]) * ky;
  const bx = (b[1] - a[1]) * kx, by = (b[0] - a[0]) * ky;
  const len2 = bx * bx + by * by;
  const t = len2 ? Math.max(0, Math.min(1, (px * bx + py * by) / len2)) : 0;
  return Math.hypot(px - bx * t, py - by * t);
}

function nearCount(coords, pins) {
  return pins.filter((r) => {
    const p = [r.lat, r.lon];
    for (let i = 1; i < coords.length; i++) {
      if (distToSegM(p, coords[i - 1], coords[i]) <= PROBLEM_RADIUS) return true;
    }
    return false;
  }).length;
}

export function initRoute({ map, api, getPins }) {
  const layer = L.layerGroup().addTo(map);
  let mode = 'idle';   // idle | pickA | pickB | loading | done
  let start = null;
  let end = null;
  let token = 0;

  const lengthOf = (coords) =>
    coords.slice(1).reduce((sum, c, i) => sum + map.distance(coords[i], c), 0);

  function marker(ll, text, bg) {
    return L.marker(ll, {
      interactive: false,
      icon: L.divIcon({
        className: `flex items-center justify-center rounded-full border-2 border-white text-sm font-bold text-white shadow-lg ${bg}`,
        html: text,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
    }).addTo(layer);
  }

  function setMode(m) {
    mode = m;
    const picking = m === 'pickA' || m === 'pickB';
    $('routeBtn').hidden = m !== 'idle';
    $('routePanel').hidden = !picking;
    $('routeCard').hidden = !(m === 'loading' || m === 'done');
    $('fab').hidden = m !== 'idle';
    $('hotspotsBtn').hidden = m !== 'idle';
    map.getContainer().style.cursor = picking ? 'crosshair' : '';
    if (m === 'pickA') $('routeHint').textContent = 'Tap your start point';
    if (m === 'pickB') $('routeHint').textContent = 'Now tap your destination';
  }

  function clear() {
    token++;
    layer.clearLayers();
    start = null;
    end = null;
  }
  const exit = () => { clear(); setMode('idle'); };
  const restart = () => { clear(); setMode('pickA'); };

  function show(r) {
    const d = r.direct;
    const s = r.safer;
    const dLen = d.length ?? lengthOf(d.coords);
    const sLen = s.length ?? lengthOf(s.coords);

    layer.addLayer(L.polyline(d.coords, { color: '#6b7280', weight: 5, opacity: 0.9, dashArray: '8 8' }));
    layer.addLayer(L.polyline(s.coords, { color: '#2563eb', weight: 6, opacity: 0.95 }));
    map.fitBounds(L.latLngBounds([...d.coords, ...s.coords]), {
      paddingTopLeft: [40, 90],
      paddingBottomRight: [40, 260],
    });

    let dN = null;
    let sN = null;
    let summary = '';
    let note = '';
    if (r.demo) {
      note = r.failed
        ? "Couldn't reach the routing service, so this is a demo route (prototype)."
        : 'Demo route (prototype), not computed from the street network.';
    } else {
      const pins = getPins();
      dN = nearCount(d.coords, pins);
      sN = nearCount(s.coords, pins);
      const extra = sLen - dLen;
      const avoided = Math.max(0, dN - sN);
      summary = extra < 15
        ? 'The direct route is already the best one we found.'
        : `Safer route is +${fmt(extra)}${avoided ? ` and avoids ${plural(avoided)}` : ''}.`;
    }

    const row = (swatch, name, len, n) => `
      <div class="flex items-center gap-2 text-sm">
        ${swatch}<b>${name}</b>
        <span class="text-gray-600">${fmt(len)}${n == null ? '' : ` · ${plural(n)} nearby`}</span>
      </div>`;

    $('routeBody').innerHTML =
      row('<span class="h-1.5 w-7 shrink-0 rounded bg-blue-600"></span>', 'Safer', sLen, sN) +
      row('<span class="w-7 shrink-0 border-t-4 border-dashed border-gray-500"></span>', 'Direct', dLen, dN) +
      (summary ? `<p class="m-0 text-[15px] font-medium">${summary}</p>` : '') +
      (note ? `<p class="m-0 text-xs text-gray-500">${note}</p>` : '');
    setMode('done');
  }

  async function run() {
    const my = ++token;
    setMode('loading');
    $('routeBody').innerHTML = '<p class="m-0 text-sm text-gray-700">Finding the safer route…</p>';
    let r;
    try {
      r = await api.getRoute(start, end);
    } catch (e) {
      console.error(e);
      r = { ...api.mockRoute(start, end), demo: true, failed: true };
    }
    if (my !== token) return;   // cleared while loading
    show(r);
  }

  map.on('click', (e) => {
    if (mode === 'pickA') {
      start = e.latlng;
      marker(start, 'A', 'bg-green-600');
      setMode('pickB');
    } else if (mode === 'pickB') {
      if (map.distance(start, e.latlng) < 30) {
        $('routeHint').textContent = 'Too close. Tap a different destination';
        return;
      }
      end = e.latlng;
      marker(end, 'B', 'bg-red-600');
      run();
    }
  });

  $('routeBtn').addEventListener('click', restart);
  $('routeCancel').addEventListener('click', exit);
  $('routeClose').addEventListener('click', exit);
  $('routeNew').addEventListener('click', restart);
  setMode('idle');
}