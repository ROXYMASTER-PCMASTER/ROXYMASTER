async function cargarKPI() {
  try {
    const d = await api('GET', '/api/dashboard');
    if (d.exito) {
      document.getElementById('kpi-usuarios').textContent = d.total_usuarios || d.stats?.total_usuarios || d.usuario?.id || 1;
      document.getElementById('kpi-pcbots').textContent = d.pcbots_conectados || d.stats?.pcbots_conectados || 0;
      document.getElementById('kpi-tokens').textContent = (d.stats_kbt?.tokens_en_circulacion || d.stats?.tokens_en_circulacion || 0).toFixed(0);
      document.getElementById('kpi-pedidos').textContent = d.comandos_pendientes || d.stats?.comandos_pendientes || 0;
    }
  } catch(e) { console.error(e); }
}
async function listarUsuarios() {
  try {
    const d = await api('GET', '/api/admin/usuarios');
    const tbody = document.querySelector('#tabla-usuarios tbody');
    if ((d.ok||d.exito) && tbody) tbody.innerHTML = (d.usuarios||d.datos||[]).map(u => `<tr><td>${u.id}</td><td>${u.email}</td><td>${u.rol}</td><td>${u.activo}</td></tr>`).join('');
  } catch(e) { console.error(e); }
}
async function listarPerfiles() {
  try {
    const d = await api('GET', '/api/admin/perfiles');
    const tbody = document.querySelector('#tabla-perfiles tbody');
    if ((d.ok||d.exito) && tbody) tbody.innerHTML = (d.perfiles||d.datos||[]).map(p => `<tr><td>${p.id}</td><td>${p.nombre_perfil}</td><td>${p.estado}</td></tr>`).join('') || '';
  } catch(e) { console.error(e); }
}
async function listarSesiones() {
  try {
    const d = await api('GET', '/api/admin/sesiones');
    const tbody = document.querySelector('#tabla-sesiones tbody');
    if ((d.ok||d.exito) && tbody) tbody.innerHTML = (d.sesiones||d.datos||[]).map(s => `<tr><td>${(s.token||'').substring(0,8)}...</td><td>${s.email||s.usuario||''}</td><td>${s.rol||''}</td></tr>`).join('') || '';
  } catch(e) { console.error(e); }
}
async function cargarMonitoreo() {
  try {
    const d = await api('GET', '/api/dashboard');
    if (d.exito) {
      const stats = d.stats || d;
      document.getElementById('mon-pcbots').textContent = stats.pcbots_conectados || d.usuario?.pcbot_id ? 1 : 0;
      document.getElementById('mon-perfiles').textContent = stats.perfiles_activos || 0;
      document.getElementById('mon-pedidos').textContent = stats.comandos_pendientes || 0;
    }
  } catch(e) { console.error(e); }
}
async function cargarTokenomia() {
  try {
    const d = await api('GET', '/api/admin/variables');
    const div = document.getElementById('tab-tokenomia');
    if ((d.ok||d.exito) && div) {
      const vars = d.variables || d.datos || {};
      div.innerHTML = '<h3>variables economicas</h3><div class="row">' + 
        Object.entries(vars).map(([k,v]) => `<div class="col-md-4"><label>${k}</label><input value="${typeof v === 'string' ? v : JSON.stringify(v)}" onchange="guardarVariable('${k}', this.value)" class="form-control mb-2"></div>`).join('') + 
        '</div><button class="btn btn-primario mt-3" onclick="location.reload()">restablecer</button>';
    }
  } catch(e) { console.error(e); }
}
function guardarVariable(clave, valor) {
  api('POST', '/api/admin/variables', { nombre: clave, valor: valor }).then(d => {
    if (d.ok || d.exito) mostrarToast('variable guardada', 'success');
  });
}
setInterval(() => { if (!document.getElementById('login-screen').classList.contains('hidden')) cargarKPI(); }, 30000);
