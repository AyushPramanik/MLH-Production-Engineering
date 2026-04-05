// Dashboard: compact metrics (Latency, Traffic, Errors, Saturation)
(function () {
  const MAX_POINTS = 30;

  function ctxFor(id) {
    const el = document.getElementById(id);
    return el ? el.getContext('2d') : null;
  }

  const latencyCtx = ctxFor('latencyChart');
  const trafficCtx = ctxFor('trafficChart');
  const errorsCtx = ctxFor('errorsChart');
  const satCtx = ctxFor('saturationChart');

  const labels = [];
  const latencyData = [];
  const trafficData = [];
  const errorsData = [];

  let latencyChart = null;
  let trafficChart = null;
  let errorsChart = null;
  let saturationChart = null;

  if (latencyCtx) {
    latencyChart = new Chart(latencyCtx, {
      type: 'line',
      data: { labels, datasets: [{ label: 'Latency (ms)', data: latencyData, borderColor: '#ffc107', backgroundColor: 'rgba(255,193,7,0.06)', fill: true }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, elements: { point: { radius: 0 }, line: { tension: 0.3 } }, scales: { x: { display: false }, y: { beginAtZero: true } } }
    });
  }

  if (trafficCtx) {
    trafficChart = new Chart(trafficCtx, {
      type: 'line',
      data: { labels, datasets: [{ label: 'Req/s', data: trafficData, borderColor: '#0dcaf0', backgroundColor: 'rgba(13,202,240,0.04)', fill: true }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, elements: { point: { radius: 0 }, line: { tension: 0.3 } }, scales: { x: { display: false }, y: { beginAtZero: true } } }
    });
  }

  if (errorsCtx) {
    errorsChart = new Chart(errorsCtx, {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Errors', data: errorsData, backgroundColor: '#dc3545' }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
  }

  if (satCtx) {
    saturationChart = new Chart(satCtx, {
      type: 'doughnut',
      data: { labels: ['Used', 'Free'], datasets: [{ data: [0, 100], backgroundColor: ['#6610f2', '#343a40'] }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, cutout: '60%' }
    });
  }

  function fmtUptime(sec) {
    if (!sec && sec !== 0) return '—';
    sec = Math.round(sec);
    const days = Math.floor(sec / 86400);
    sec %= 86400;
    const hr = Math.floor(sec / 3600);
    sec %= 3600;
    const min = Math.floor(sec / 60);
    const s = sec % 60;
    return `${days}d ${hr}h ${min}m ${s}s`;
  }

  async function fetchJSON(path) {
    try {
      const res = await fetch(path, { cache: 'no-store' });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json();
    } catch (e) {
      return { __error: e.message };
    }
  }

  async function update() {
    const [metrics, alertStatus, logs] = await Promise.all([
      fetchJSON('/metrics'),
      fetchJSON('/alert-status'),
      fetchJSON('/logs?limit=25')
    ]);

    if (!metrics.__error) {
      const t = new Date().toLocaleTimeString();
      labels.push(t);
      latencyData.push(metrics.latency?.avg_ms || 0);
      trafficData.push(metrics.traffic_rps || 0);
      errorsData.push(metrics.requests?.errors || 0);
      if (labels.length > MAX_POINTS) { labels.shift(); latencyData.shift(); trafficData.shift(); errorsData.shift(); }

      if (latencyChart) latencyChart.update();
      if (trafficChart) trafficChart.update();
      if (errorsChart) errorsChart.update();

      const sat = Math.round(metrics.saturation || 0);
      if (saturationChart) {
        saturationChart.data.datasets[0].data = [sat, Math.max(0, 100 - sat)];
        saturationChart.update();
      }

      document.getElementById('latency-p95') && (document.getElementById('latency-p95').textContent = metrics.latency?.p95_ms ?? '—');
      document.getElementById('uptime') && (document.getElementById('uptime').textContent = fmtUptime(metrics.uptime_seconds));
      document.getElementById('memory-info') && (document.getElementById('memory-info').textContent = `Memory: ${metrics.memory.used_mb} MB used / ${metrics.memory.total_mb} MB (${metrics.memory.percent}%)`);
      document.getElementById('cpu-info') && (document.getElementById('cpu-info').textContent = `CPU: ${metrics.cpu_percent}%`);
      const svc = document.getElementById('service-status');
      if (svc) { svc.textContent = 'Running'; svc.classList.remove('text-danger'); svc.classList.add('text-success'); }
    }

    if (!alertStatus.__error) {
      const s = document.getElementById('alert-status');
      const parts = [];
      const alerts = alertStatus.alerts || {};
      for (const k in alerts) parts.push(`${k}: ${alerts[k].firing ? 'FIRING' : 'OK'}`);
      if (s) s.textContent = parts.join(' | ');
    } else {
      const s = document.getElementById('alert-status'); if (s) s.textContent = 'alert manager not running';
    }

    if (!logs.__error) {
      const pre = document.getElementById('logs');
      if (pre) {
        if (Array.isArray(logs) && logs.length) {
          pre.textContent = logs.slice().reverse().map(l => JSON.stringify(l)).join('\n\n');
        } else {
          pre.textContent = 'No logs';
        }
      }
    }
  }

  // Initial poll and interval
  update();
  setInterval(update, 3000);
})();