const state = { observations: [], filtered: [], summary: null, selected: null };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const fmt = (value, digits = 0) => Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

async function load() {
  const [observations, summary] = await Promise.all([
    fetch('/api/observations.json').then((r) => {
      if (!r.ok) throw new Error(`Observations request failed: ${r.status}`);
      return r.json();
    }),
    fetch('/api/summary.json').then((r) => {
      if (!r.ok) throw new Error(`Summary request failed: ${r.status}`);
      return r.json();
    }),
  ]);
  state.observations = observations;
  state.filtered = observations;
  state.summary = summary;
  populateSamples();
  applyFilter();
  renderSummary();
  renderHarmonization();
  renderCalendar();
  selectObservation(observations[0].id, false);
}

function applyFilter() {
  const sensor = $('#sensorSelect').value;
  state.filtered = sensor === 'ALL' ? state.observations : state.observations.filter((d) => d.sensor === sensor);
  renderMap();
  renderTable();
}

function renderSummary() {
  const t = state.summary.totals;
  $('#totalDetections').textContent = fmt(t.detections);
  $('#railCount').textContent = fmt(t.detections);
  $('#labCount').textContent = fmt(t.detections);
  $('#dataCount').textContent = fmt(t.detections);
  $('#totalFrp').textContent = `${fmt(t.total_frp, 1)} MW`;
  $('#gridCount').textContent = fmt(t.grids);
  $('#unusualCount').textContent = fmt(t.unusual);
}

function renderMap() {
  const map = $('#worldMap');
  map.querySelectorAll('.hotspot').forEach((node) => node.remove());
  map.querySelector('.map-empty').style.display = state.filtered.length ? 'none' : 'grid';
  state.filtered.forEach((d) => {
    const button = document.createElement('button');
    button.className = `hotspot ${d.sensor.toLowerCase()}`;
    button.style.left = `${((d.longitude + 180) / 360) * 100}%`;
    button.style.top = `${((90 - d.latitude) / 180) * 100}%`;
    button.style.opacity = String(.48 + d.hfai * .52);
    button.title = `${d.sensor} · ${d.frp} MW · HFAI ${d.hfai}`;
    button.setAttribute('aria-label', button.title);
    button.addEventListener('click', () => selectObservation(d.id, false));
    map.appendChild(button);
  });
  const highest = [...state.filtered].sort((a, b) => b.hfai - a.hfai)[0];
  if (highest) selectObservation(highest.id, false);
}

function selectObservation(id, updatePicker = true) {
  const d = state.observations.find((item) => item.id === Number(id));
  if (!d) return;
  state.selected = d;
  if (updatePicker) $('#sampleSelect').value = String(d.id);
  $$('.hotspot').forEach((node) => node.classList.toggle('selected', node.title.includes(`${d.frp} MW`) && node.title.startsWith(d.sensor)));
  $('#focusRegion').textContent = `${Number(d.latitude).toFixed(2)}°, ${Number(d.longitude).toFixed(2)}°`;
  $('#focusStatus').textContent = d.status;
  $('#focusHfai').textContent = Number(d.hfai).toFixed(2);
  $('#focusSensor').textContent = `${d.sensor} · ${d.satellite}`;
  $('#focusFrp').textContent = `${fmt(d.frp, 2)} MW`;
  $('#focusBrightness').textContent = `${fmt(d.brightness, 1)} K`;
  $('#focusAgreement').textContent = `${Math.round(d.sensor_agreement * 100)}%`;
  $('#radial').style.setProperty('--score', `${d.hfai * 360}deg`);
  fillInputs(d);
}

function populateSamples() {
  $('#sampleSelect').innerHTML = state.observations.map((d) => `<option value="${d.id}">#${String(d.id).padStart(3, '0')} · ${d.sensor} · ${d.acq_date} · ${Number(d.frp).toFixed(1)} MW</option>`).join('');
}

function fillInputs(d) {
  $('#sampleSelect').value = String(d.id);
  $('#inputLat').value = Number(d.latitude).toFixed(5);
  $('#inputLon').value = Number(d.longitude).toFixed(5);
  $('#inputBrightness').value = Number(d.brightness).toFixed(2);
  $('#inputFrp').value = Number(d.frp).toFixed(2);
  $('#inputConfidence').value = d.confidence;
  $('#inputDaynight').value = d.daynight === 'D' ? 'Day' : 'Night';
  $('#resultStatus').textContent = 'Ready to analyze';
  $('#resultScore').textContent = '—';
  $('#resultTrack').style.width = '0';
}

function analyze() {
  const d = state.selected;
  if (!d) return;
  $('#resultStatus').textContent = `${d.status} activity`;
  $('#resultScore').textContent = Number(d.hfai).toFixed(2);
  $('#resultTrack').style.width = `${d.hfai * 100}%`;
  $('#resultGrid').textContent = d.grid_id;
  $('#resultAgreement').textContent = `${Math.round(d.sensor_agreement * 100)}%`;
  $('#resultSensor').textContent = `${d.satellite} / ${d.sensor}`;
  $('#resultTime').textContent = d.datetime_utc.replace('T', ' ').replace(':00Z', ' UTC');
  const wording = d.status === 'Unusual' ? 'substantially above the prototype engineering range' : d.status === 'Elevated' ? 'above the middle of the prototype engineering range' : 'within the lower prototype engineering range';
  $('#resultText').textContent = `This ${d.sensor} thermal observation is ${wording}. It is a satellite-derived signal, not confirmation of a wildfire or a model forecast.`;
}

function renderHarmonization() {
  const max = Math.max(...state.summary.sensors.map((d) => d.detections));
  $('#sensorCards').innerHTML = state.summary.sensors.map((d) => `<article class="panel sensor-card"><p class="kicker">${d.sensor === 'MODIS' ? '≈1 KM SOURCE PRODUCT' : '≈375 M SOURCE PRODUCT'}</p><strong>${d.sensor}</strong><div class="stats"><div><small>Detections</small><b>${d.detections}</b></div><div><small>Mean FRP</small><b>${d.mean_frp} MW</b></div><div><small>Agreement</small><b>${Math.round(d.mean_agreement * 100)}%</b></div></div></article>`).join('');
  $('#sensorBars').innerHTML = state.summary.sensors.map((d) => `<div class="bar-row"><b>${d.sensor}</b><div class="bar"><i style="width:${(d.detections / max) * 100}%"></i></div><span>${d.detections}</span></div>`).join('');
}

function renderCalendar() {
  const grouped = new Map();
  state.observations.forEach((d) => {
    if (!grouped.has(d.acq_date)) grouped.set(d.acq_date, []);
    grouped.get(d.acq_date).push(d.hfai);
  });
  const days = [...grouped].map(([date, values]) => ({ date, score: values.reduce((a, b) => a + b, 0) / values.length, count: values.length })).sort((a, b) => a.date.localeCompare(b.date));
  const shown = days.slice(0, 28);
  const weekdays = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  let html = '<div></div>' + weekdays.map((d) => `<div class="head">${d}</div>`).join('');
  for (let row = 0; row < 4; row += 1) {
    html += `<div class="date-label">Period ${String(row + 1).padStart(2, '0')}</div>`;
    for (let col = 0; col < 7; col += 1) {
      const item = shown[row * 7 + col];
      if (!item) { html += '<div class="cell"></div>'; continue; }
      const hue = 215 - item.score * 195;
      const light = 18 + item.score * 32;
      html += `<div class="cell" style="background:hsl(${hue} 62% ${light}% / .9)" title="${item.date}: ${item.count} detections, HFAI ${item.score.toFixed(2)}">${item.date.slice(5)}</div>`;
    }
  }
  $('#activityCalendar').innerHTML = html;
  const top = [...days].sort((a, b) => b.score - a.score).slice(0, 3);
  $('#criticalPeriods').innerHTML = top.map((d, i) => `<article class="period-card"><span>CRITICAL PERIOD ${String(i + 1).padStart(2, '0')}</span><strong>${new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}</strong><span>${d.count} detections · mean HFAI ${d.score.toFixed(2)}</span></article>`).join('');
}

function renderTable() {
  $('#dataTable').innerHTML = state.filtered.map((d) => `<tr><td>${String(d.id).padStart(3, '0')}</td><td>${d.sensor}</td><td>${d.satellite}</td><td>${d.acq_date} ${d.acq_time}</td><td>${Number(d.latitude).toFixed(3)}, ${Number(d.longitude).toFixed(3)}</td><td>${Number(d.frp).toFixed(2)} MW</td><td>${Number(d.hfai).toFixed(2)}</td><td class="status-text ${d.status.toLowerCase()}">${d.status}</td></tr>`).join('');
}

function setView(id) {
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === id));
  $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === id));
  const titles = { overview: 'Global activity overview', harmonize: 'Sensor harmonization', calendar: 'Burning activity calendar', lab: 'Observation scenario lab', data: 'Source data explorer' };
  $('#viewTitle').textContent = titles[id];
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

$$('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
$('#sensorSelect').addEventListener('change', applyFilter);
$('#sampleSelect').addEventListener('change', (event) => selectObservation(event.target.value));
$('#analyzeButton').addEventListener('click', analyze);
$$('[data-open-lab]').forEach((button) => button.addEventListener('click', () => setView('lab')));
load().catch((error) => { console.error(error); $('.map-empty').textContent = 'Unable to load the local dataset.'; });
