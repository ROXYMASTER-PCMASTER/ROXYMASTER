const API = '';
let token = localStorage.getItem('token') || '';
let usuarioActual = null;

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (token) opts.headers['Authorization'] = 'Bearer ' + token;
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function mostrarToast(msg, tipo) {
  const t = document.createElement('div'); t.className = 'toast';
  t.style.background = tipo === 'error' ? 'var(--rojo)' : 'var(--verde)'; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 3000);
}

async function login(email, password) {
  try {
    const res = await api('POST', '/api/login', { email, password });
    if (res.token) {
      token = res.token; localStorage.setItem('token', token);
      usuarioActual = res.usuario || res.email;
      document.getElementById('login-screen').classList.add('hidden');
      document.getElementById('dashboard-screen').classList.remove('hidden');
      document.getElementById('usuario_email').textContent = email;
      cargarKPI(); cargarTabActual();
    } else {
      mostrarToast(res.error || 'credenciales invalidas', 'error');
    }
  } catch (e) { mostrarToast('error de conexion', 'error'); }
}

function cerrarSesion() {
  token = '';
  localStorage.clear();
  location.href = '/publico/login.html';
}

function switchTab(id) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.sidebar nav button').forEach(el => el.classList.remove('active'));
  const target = document.getElementById('tab-' + id);
  if (target) target.classList.remove('hidden');
  const btn = document.querySelector(`.sidebar nav button[onclick*="'${id}'"]`);
  if (btn) btn.classList.add('active');
  cargarTabActual();
}

function cargarTabActual() {
  const active = document.querySelector('.tab-content:not(.hidden)');
  if (!active) return;
  const id = active.id.replace('tab-', '');
  if (id === 'kpi') cargarKPI();
  else if (id === 'usuarios') listarUsuarios();
  else if (id === 'perfiles') listarPerfiles();
  else if (id === 'sesiones') listarSesiones();
  else if (id === 'monitoreo') cargarMonitoreo();
  else if (id === 'tokenomia') cargarTokenomia();
}

document.addEventListener('DOMContentLoaded', () => {
  if (token) {
    api('GET', '/api/verify').then(d => {
      if (d.exito) {
        document.getElementById('login-screen').classList.add('hidden');
        document.getElementById('dashboard-screen').classList.remove('hidden');
        cargarKPI();
      } else { token = ''; localStorage.removeItem('token'); }
    }).catch(() => { token = ''; localStorage.removeItem('token'); });
  }
  document.getElementById('login-pass').addEventListener('keydown', e => { if (e.key === 'Enter') loginFromForm(); });
});