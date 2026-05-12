// dashboard_admin.js - panel de administracion roxymaster v8.3
// sidebar elegante con mayusculas, drill-down 3 niveles, modales crud, roles
// todos los nombres en minusculas, utf-8 sin bom

let token = "";
let usuarioActual = "";
let rolActual = "";
let modalCallback = null;
let kpisCache = {};
let monitoreoInterval = null;
let wsMonitoreo = null;
let usuariosCache = [];
let perfilesCache = [];

// ============================================================
// helpers
// ============================================================
function escHtml(s) {
  if (s === null || s === undefined) return "";
  var m = {"\u0026":"\u0026amp;","\u003c":"\u0026lt;","\u003e":"\u0026gt;",'"':"\u0026quot;"};
  return String(s).replace(/[&<>"]/g,function(c){return m[c];});
}

function formatearFecha(f) {
  if (!f) return "--";
  try {
    const d = new Date(f);
    if (isNaN(d.getTime())) return f;
    return d.toLocaleDateString("es-PE", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"});
  } catch(e) { return f; }
}

function badgeRol(rol) {
  const clase = {"admin":"badge-admin","usuario":"badge-user","granjero":"badge-granjero","moderador":"badge-moderador","dueno":"badge-dueno"};
  return '<span class="badge ' + (clase[rol]||"badge-user") + '">' + escHtml(rol) + '</span>';
}

function badgeEstado(estado) {
  if (estado === 1 || estado === "1" || estado === "activo") return '<span class="badge badge-activo">activo</span>';
  return '<span class="badge badge-inactivo">inactivo</span>';
}

function mostrarToast(msg, tipo) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (tipo === "error" ? " error" : tipo === "success" ? " success" : "");
  setTimeout(() => { t.className = "toast"; }, 3500);
}

// ============================================================
// api wrapper
// ============================================================
async function api(method, url, body) {
  const headers = {"Content-Type":"application/json"};
  if (token) headers["Authorization"] = "Bearer " + token;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg;
    try { const j = await r.json(); msg = j.detail || j.mensaje || "error " + r.status; } catch(e) { msg = "error " + r.status; }
    throw new Error(msg);
  }
  try { return await r.json(); } catch(e) { return {}; }
}

// ============================================================
// switch de pestañas (sidebar con sombreado persistente)
// ============================================================
function switchTab(nombre) {
  // ocultar todos los tab-content
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  // mostrar el seleccionado
  const target = document.getElementById("tab-content-" + nombre);
  if (target) target.classList.add("active");

  // sidebar: remover active de todos, poner en el seleccionado
  document.querySelectorAll(".admin-sidebar nav button").forEach(b => b.classList.remove("active"));
  const navBtn = document.getElementById("nav-" + nombre);
  if (navBtn) navBtn.classList.add("active");

  // actualizar titulo
  const titulo = document.getElementById("tab-titulo");
  const labels = {kpi:"panel kpi", usuarios:"usuarios", sesiones:"sesiones", perfiles:"perfiles", pcs:"pcs registradas", retiros:"retiros", mensajes:"mensajes", monitoreo:"monitoreo", tokenomia:"tokenomia", proyecciones:"proyecciones", seguridad:"seguridad"};
  if (titulo) titulo.textContent = labels[nombre] || nombre;

  // cargar datos segun tab
  if (nombre === "usuarios") listarUsuarios();
  else if (nombre === "sesiones") listarSesiones();
  else if (nombre === "perfiles") listarPerfiles();
  else if (nombre === "pcs") listarPcs();
  else if (nombre === "retiros") listarRetiros();
  else if (nombre === "mensajes") listarMensajesAdmin();
  else if (nombre === "kpi") { cargarKPI(); }
  else if (nombre === "monitoreo") { cargarMonitoreo(); }
  else if (nombre === "tokenomia") { cargarTokenomia(); }
}

// ============================================================
// KPI - tarjetas con sombreado persistente y drill-down
// ============================================================
async function cargarKPI() {
  try {
    const r = await api("GET", "/api/admin/kpi");
    const d = r.kpi || r;
    document.getElementById("kpi-usuarios").textContent = d.usuarios_totales ?? d.usuarios ?? 0;
    document.getElementById("kpi-pcbots").textContent = d.pcbots_conectados ?? d.pcbots ?? 0;
    document.getElementById("kpi-tokens").textContent = d.kbt_circulando ?? d.tokens ?? 0;
    document.getElementById("kpi-pedidos").textContent = d.pedidos_pendientes ?? d.pedidos ?? 0;
    document.getElementById("kpi-perfiles").textContent = d.perfiles_activos ?? d.perfiles ?? 0;
    document.getElementById("kpi-ingresos").textContent = d.ingresos_kbt_hoy ?? d.ingresos ?? 0;
    kpisCache = d;
  } catch(e) {
    mostrarToast("error cargando kpi: " + e.message, "error");
  }
}

let kpiSeleccionado = null;
let kpiItemSeleccionado = null;

function seleccionarKPI(tipo, card) {
  // toggle: si es la misma, cierro
  if (kpiSeleccionado === tipo) {
    document.querySelectorAll(".kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
    document.getElementById("kpi-detalle").classList.remove("show");
    kpiSeleccionado = null;
    kpiItemSeleccionado = null;
    return;
  }
  // quitar sombreado de todas, sombrear esta
  document.querySelectorAll(".kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
  card.classList.add("kpi-selected");
  kpiSeleccionado = tipo;
  kpiItemSeleccionado = null;
  mostrarDetalleKPI(tipo);
}

async function mostrarDetalleKPI(tipo) {
  const cont = document.getElementById("kpi-detalle");
  cont.innerHTML = '<div class="kpi-detalle-loading">cargando detalle...</div>';
  cont.classList.add("show");

  try {
    // intentar obtener datos detallados del endpoint o usar cache
    let data = {};
    try {
      const r = await api("GET", "/api/admin/kpi/detalle?tipo=" + encodeURIComponent(tipo));
      data = r.detalle || r;
    } catch(e) {
      // fallback: usar datos del cache
      data = {};
    }

    let html = '<div class="kpi-detalle-header">Detalle: ' + tipo.charAt(0).toUpperCase() + tipo.slice(1) + '</div>';

    // nivel 2: items clickeables
    const items = getItemsPorTipo(tipo, kpisCache);
    if (items && items.length) {
      html += '<div class="kpi-detalle-grid">';
      items.forEach((item, idx) => {
        html += '<div class="kpi-detalle-item" onclick="seleccionarItemKPI(' + idx + ', this)" data-item-idx="' + idx + '">' +
          '<span class="item-label">' + escHtml(item.label) + '</span>' +
          '<span class="item-val">' + escHtml(item.val) + '</span></div>';
      });
      html += '</div>';
    }

    // nivel 3: panel expandible
    html += '<div id="n3-panel" class="n3-panel"></div>';
    cont.innerHTML = html;
  } catch(e) {
    cont.innerHTML = '<div class="kpi-detalle-error">error: ' + escHtml(e.message) + '</div>';
  }
}

function getItemsPorTipo(tipo, cache) {
  const mapa = {
    usuarios: [
      {label: "Activos", val: cache.usuarios_activos ?? "?"},
      {label: "Inactivos", val: cache.usuarios_inactivos ?? "?"},
      {label: "Admins", val: cache.administradores ?? "?"},
      {label: "Registrados Hoy", val: cache.nuevos_hoy ?? "?"},
      {label: "Con Wallet", val: cache.con_wallet ?? "?"},
    ],
    pcbots: [
      {label: "Conectados", val: cache.pcbots_conectados ?? "?"},
      {label: "Desconectados", val: cache.pcbots_desconectados ?? "?"},
      {label: "Online %", val: cache.pcbots_online_pct ?? "?"},
    ],
    tokens: [
      {label: "En Circulacion", val: cache.kbt_circulando ?? "?"},
      {label: "Minados Hoy", val: cache.minados_hoy ?? "?"},
      {label: "Transacciones Hoy", val: cache.transacciones_hoy ?? "?"},
    ],
    pedidos: [
      {label: "Pendientes", val: cache.pedidos_pendientes ?? "?"},
      {label: "Completados Hoy", val: cache.completados_hoy ?? "?"},
      {label: "Cancelados", val: cache.cancelados ?? "?"},
    ],
    perfiles: [
      {label: "Activos", val: cache.perfiles_activos ?? "?"},
      {label: "Inactivos", val: cache.perfiles_inactivos ?? "?"},
      {label: "Total", val: (cache.perfiles_activos ?? 0) + (cache.perfiles_inactivos ?? 0)},
    ],
    ingresos: [
      {label: "Hoy", val: cache.ingresos_kbt_hoy ?? "?"},
      {label: "Esta Semana", val: cache.ingresos_semana ?? "?"},
      {label: "Este Mes", val: cache.ingresos_mes ?? "?"},
    ],
  };
  return mapa[tipo] || null;
}

function seleccionarItemKPI(idx, el) {
  // quitar seleccion de otros items
  document.querySelectorAll(".kpi-detalle-item.kpi-item-selected").forEach(c => c.classList.remove("kpi-item-selected"));
  el.classList.add("kpi-item-selected");
  kpiItemSeleccionado = idx;

  // cargar nivel 3
  const n3 = document.getElementById("n3-panel");
  const tipo = kpiSeleccionado;
  n3.innerHTML = '<div class="n3-loading">cargando datos detallados...</div>';
  n3.classList.add("show");

  // mostrar datos segun tipo e indice
  mostrarN3(tipo, idx);
}

async function mostrarN3(tipo, idx) {
  const n3 = document.getElementById("n3-panel");
  try {
    let tabla = "";
    if (tipo === "usuarios" && idx === 0) {
      // Activos: listar usuarios
      const r = await api("GET", "/api/admin/usuarios?q=&estado=activo");
      const lista = Array.isArray(r) ? r : (r.usuarios || []);
      tabla = '<table class="n3-tabla"><thead><tr><th>ID</th><th>Email</th><th>Rol</th><th>Pcbot</th><th>Registro</th></tr></thead><tbody>' +
        (lista.length ? lista.map(u => '<tr><td>' + u.id + '</td><td>' + escHtml(u.email) + '</td><td>' + badgeRol(u.rol) + '</td><td>' + escHtml(u.pcbot_id || "--") + '</td><td>' + formatearFecha(u.fecha_registro) + '</td></tr>').join("") :
        '<tr><td colspan="5" class="empty-msg">sin datos</td></tr>') + '</tbody></table>';
    } else if (tipo === "usuarios" && idx === 2) {
      // Admins
      const r = await api("GET", "/api/admin/usuarios?q=&rol=admin");
      const lista = Array.isArray(r) ? r : (r.usuarios || []);
      tabla = '<table class="n3-tabla"><thead><tr><th>ID</th><th>Email</th><th>Rol</th><th>Pcbot</th><th>Ultimo Login</th></tr></thead><tbody>' +
        (lista.length ? lista.map(u => '<tr><td>' + u.id + '</td><td>' + escHtml(u.email) + '</td><td>' + badgeRol(u.rol) + '</td><td>' + escHtml(u.pcbot_id || "--") + '</td><td>' + formatearFecha(u.ultimo_login) + '</td></tr>').join("") :
        '<tr><td colspan="5" class="empty-msg">sin datos</td></tr>') + '</tbody></table>';
    } else if (tipo === "perfiles" && idx === 0) {
      // Perfiles activos
      const r = await api("GET", "/api/admin/perfiles?estado=activo");
      const lista = Array.isArray(r) ? r : (r.perfiles || []);
      tabla = '<table class="n3-tabla"><thead><tr><th>ID</th><th>Nombre</th><th>Usuario</th><th>Horas Conexion</th><th>Ultimo Heartbeat</th></tr></thead><tbody>' +
        (lista.length ? lista.map(p => '<tr><td>' + p.id + '</td><td>' + escHtml(p.nombre_perfil || "--") + '</td><td>' + escHtml(p.dueno_email || p.usuario_id) + '</td><td>' + escHtml(p.horas_conexion || 0) + 'h</td><td>' + formatearFecha(p.ultimo_heartbeat) + '</td></tr>').join("") :
        '<tr><td colspan="5" class="empty-msg">sin datos</td></tr>') + '</tbody></table>';
    } else {
      tabla = '<p class="empty-msg">detalle expandible proximamente para ' + escHtml(tipo) + ' #' + idx + '</p>';
    }
    n3.innerHTML = tabla;
  } catch(e) {
    n3.innerHTML = '<p class="empty-msg">error: ' + escHtml(e.message) + '</p>';
  }
}

// ============================================================
// usuarios
// ============================================================
let usuarioExpandido = null;

async function listarUsuarios() {
  try {
    const q = document.getElementById("filtro-usuarios").value;
    const rol = document.getElementById("filtro-rol-usuarios").value;
    const estadoEl = document.getElementById("filtro-estado-usuarios");
    const estado = estadoEl ? estadoEl.value : "";
    let url = "/api/admin/usuarios?q=" + encodeURIComponent(q);
    if (rol) url += "&rol=" + encodeURIComponent(rol);
    if (estado) url += "&estado=" + encodeURIComponent(estado);
    const r = await api("GET", url);
    const lista = Array.isArray(r) ? r : (r.usuarios || []);
    usuariosCache = lista;
    const tbody = document.getElementById("tbody-usuarios");
    if (!lista.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">sin usuarios</td></tr>'; return; }
    tbody.innerHTML = lista.map(u =>
      '<tr class="fila-usuario" onclick="toggleDetalleUsuario(' + u.id + ')">' +
      '<td>' + u.id + '</td>' +
      '<td>' + escHtml(u.email) + '</td>' +
      '<td>' + badgeRol(u.rol) + '</td>' +
      '<td>' + badgeEstado(u.activo) + '</td>' +
      '<td>' + escHtml(u.pcbot_id || "--") + '</td>' +
      '<td>' + escHtml(u.nivel_fiabilidad || "--") + '</td>' +
      '<td>' +
        '<button class="btn-accion" onclick="event.stopPropagation(); mostrarModalEditarUsuario(' + u.id + ')">editar</button>' +
        '<button class="btn-accion danger" onclick="event.stopPropagation(); mostrarModalEliminarUsuario(' + u.id + ')">eliminar</button>' +
      '</td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

function filtrarUsuarios() { listarUsuarios(); }

function toggleDetalleUsuario(id) {
  const row = document.querySelector(".detalle-usuario[data-id='" + id + "']");
  if (row) { row.remove(); usuarioExpandido = null; return; }
  // cerrar otro expandido
  document.querySelectorAll(".detalle-usuario").forEach(el => el.remove());
  mostrarDetalleUsuario(id);
}

function mostrarDetalleUsuario(id) {
  const u = usuariosCache.find(x => x.id == id);
  if (!u) return;
  const tbody = document.getElementById("tbody-usuarios");
  const tr = document.createElement("tr");
  tr.className = "detalle-usuario";
  tr.setAttribute("data-id", id);
  tr.innerHTML = '<td colspan="7">' +
    '<div class="usuario-detalle-grid">' +
      '<div class="detalle-campo"><span class="campo-label">ID</span><span class="campo-val">' + u.id + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Email</span><span class="campo-val">' + escHtml(u.email) + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Username</span><span class="campo-val">' + escHtml(u.username || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Rol</span><span class="campo-val">' + badgeRol(u.rol) + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Wallet</span><span class="campo-val">' + escHtml(u.wallet || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Codigo Referido</span><span class="campo-val">' + escHtml(u.codigo_referido || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Referido Por</span><span class="campo-val">' + escHtml(u.referido_por || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Confianza</span><span class="campo-val">' + escHtml(u.nivel_fiabilidad || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Pcbot ID</span><span class="campo-val">' + escHtml(u.pcbot_id || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Modo</span><span class="campo-val">' + escHtml(u.modo || "--") + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Ultimo Login</span><span class="campo-val">' + formatearFecha(u.ultimo_login) + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Registro</span><span class="campo-val">' + formatearFecha(u.fecha_registro) + '</span></div>' +
      '<div class="detalle-campo"><span class="campo-label">Uptime</span><span class="campo-val">' + (u.uptime_horas || 0) + 'h</span></div>' +
    '</div></td>';
  // insertar despues de la fila padre
  const ref = tbody.querySelector(".fila-usuario td:first-child") ? tbody.querySelector(".fila-usuario td:first-child").parentElement : null;
  if (ref) ref.parentElement.insertBefore(tr, ref.nextSibling);
}

// ============================================================
// sesiones
// ============================================================
async function listarSesiones() {
  try {
    const r = await api("GET", "/api/admin/sesiones");
    const lista = Array.isArray(r) ? r : (r.sesiones || []);
    const tbody = document.getElementById("tbody-sesiones");
    if (!lista.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">sin sesiones activas</td></tr>'; return; }
    tbody.innerHTML = lista.map(s =>
      '<tr><td>' + escHtml((s.token || "").substring(0, 12) + "...") + '</td>' +
      '<td>' + escHtml(s.email) + '</td>' +
      '<td>' + badgeRol(s.rol) + '</td>' +
      '<td>' + formatearFecha(s.fecha_expiracion) + '</td>' +
      '<td><button class="btn-accion danger" onclick="cerrarSesionEspecifica(\'' + s.token + '\')">revocar</button></td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

async function cerrarSesionEspecifica(tokenSesion) {
  try {
    await api("DELETE", "/api/admin/sesiones/" + encodeURIComponent(tokenSesion));
    mostrarToast("sesion revocada", "success");
    listarSesiones();
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

// ============================================================
// perfiles (agrupados por usuario)
// ============================================================
let perfilExpandido = null;

async function listarPerfiles() {
  try {
    const q = document.getElementById("filtro-perfiles").value;
    const estado = document.getElementById("filtro-estado-perfiles").value;
    let url = "/api/admin/perfiles?q=" + encodeURIComponent(q);
    if (estado) url += "&estado=" + encodeURIComponent(estado);
    const r = await api("GET", url);
    const lista = Array.isArray(r) ? r : (r.perfiles || []);
    perfilesCache = lista;
    // agrupar por usuario
    const grupos = {};
    lista.forEach(p => {
      const key = p.usuario_id + "_" + (p.dueno_email || "");
      if (!grupos[key]) grupos[key] = { usuario_id: p.usuario_id, email: p.dueno_email || "--", perfiles: [] };
      grupos[key].perfiles.push(p);
    });
    const tbody = document.getElementById("tbody-perfiles");
    const entries = Object.values(grupos);
    if (!entries.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">sin perfiles</td></tr>'; return; }
    tbody.innerHTML = entries.map(g =>
      '<tr class="fila-perfil-usuario" onclick="toggleDetallePerfil(' + g.usuario_id + ')">' +
      '<td>' + g.usuario_id + '</td>' +
      '<td>' + escHtml(g.email) + '</td>' +
      '<td>' + badgeEstado(g.perfiles.some(p => p.estado === "activo") ? "activo" : "inactivo") + '</td>' +
      '<td>' + g.perfiles.length + ' perfiles</td>' +
      '<td><button class="btn-accion" onclick="event.stopPropagation(); mostrarModalCrearPerfil(' + g.usuario_id + ')">+ perfil</button></td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

function filtrarPerfiles() { listarPerfiles(); }

function toggleDetallePerfil(usuarioId) {
  const row = document.querySelector(".detalle-perfil[data-uid='" + usuarioId + "']");
  if (row) { row.remove(); return; }
  document.querySelectorAll(".detalle-perfil").forEach(el => el.remove());
  const perfiles = perfilesCache.filter(p => p.usuario_id == usuarioId);
  const tbody = document.getElementById("tbody-perfiles");
  const tr = document.createElement("tr");
  tr.className = "detalle-perfil";
  tr.setAttribute("data-uid", usuarioId);
  let html = '<td colspan="5"><table class="inner-table"><thead><tr><th>ID</th><th>Nombre</th><th>Tipo</th><th>Estado</th><th>IP WAN</th><th>Horas Conexion</th><th>Heartbeat</th><th>Accion</th></tr></thead><tbody>';
  perfiles.forEach(p => {
    html += '<tr><td>' + p.id + '</td><td>' + escHtml(p.nombre_perfil || "--") + '</td><td>' + escHtml(p.tipo) + '</td><td>' + badgeEstado(p.estado === "activo" ? "activo" : "inactivo") + '</td>' +
      '<td>' + escHtml(p.ip_wan || "--") + '</td><td>' + escHtml(p.horas_conexion || 0) + 'h</td><td>' + formatearFecha(p.ultimo_heartbeat) + '</td>' +
      '<td><button class="btn-accion" onclick="mostrarModalEditarPerfil(' + p.id + ')">editar</button>' +
      '<button class="btn-accion danger" onclick="mostrarModalEliminarPerfil(' + p.id + ')">x</button></td></tr>';
  });
  html += '</tbody></table></td>';
  tr.innerHTML = html;
  const ref = tbody.querySelector(".fila-perfil-usuario td:first-child") ? tbody.querySelector(".fila-perfil-usuario td:first-child").parentElement : null;
  if (ref) ref.parentElement.insertBefore(tr, ref.nextSibling);
}

// ============================================================
// pcs
// ============================================================
async function listarPcs() {
  try {
    const modo = document.getElementById("filtro-modo-pcs").value;
    let url = "/api/admin/pcs?q=";
    if (modo) url += "&modo=" + encodeURIComponent(modo);
    const r = await api("GET", url);
    const lista = Array.isArray(r) ? r : (r.pcs || []);
    const tbody = document.getElementById("tbody-pcs");
    if (!lista.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">ninguna pc registrada</td></tr>'; return; }
    tbody.innerHTML = lista.map(p =>
      '<tr><td>' + escHtml(p.pcbot_id) + '</td><td>' + escHtml(p.email) + '</td><td>' + escHtml(p.modo || "desconocido") + '</td><td>' + escHtml(p.ultimo_login ? formatearFecha(p.ultimo_login) : "--") + '</td><td>' + escHtml(p.perfiles_asociados || 0) + '</td>' +
      '<td><button class="btn-accion" onclick="mostrarModalEditarPc(' + p.id + ')">editar</button></td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

function filtrarPcs() { listarPcs(); }

// ============================================================
// retiros
// ============================================================
async function listarRetiros() {
  try {
    const estado = document.getElementById("filtro-estado-retiros").value;
    let url = "/api/admin/retiros?estado=" + encodeURIComponent(estado);
    const r = await api("GET", url);
    const lista = Array.isArray(r) ? r : (r.retiros || []);
    const tbody = document.getElementById("tbody-retiros");
    if (!lista.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">sin retiros</td></tr>'; return; }
    tbody.innerHTML = lista.map(r =>
      '<tr><td>' + escHtml(r.id) + '</td><td>' + escHtml(r.usuario_email || r.usuario_id) + '</td><td>' + escHtml(r.monto) + '</td><td><span class="badge ' + (r.estado === "aprobado" ? "badge-activo" : r.estado === "rechazado" ? "badge-inactivo" : "badge-pendiente") + '">' + escHtml(r.estado) + '</span></td><td>' + formatearFecha(r.fecha_solicitud || r.fecha) + '</td>' +
      '<td>' + (r.estado === "pendiente" ?
        '<button class="btn-accion success" onclick="aprobarRetiro(' + r.id + ')">aprobar</button><button class="btn-accion danger" onclick="rechazarRetiro(' + r.id + ')">rechazar</button>' :
        '<span class="empty-msg">--</span>') + '</td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

async function aprobarRetiro(id) {
  try {
    await api("POST", "/api/admin/retiros/procesar", { retiro_id: id, accion: "aprobar" });
    mostrarToast("retiro #" + id + " aprobado", "success");
    listarRetiros();
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

async function rechazarRetiro(id) {
  try {
    await api("POST", "/api/admin/retiros/procesar", { retiro_id: id, accion: "rechazar" });
    mostrarToast("retiro #" + id + " rechazado", "success");
    listarRetiros();
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

// ============================================================
// mensajes
// ============================================================
async function listarMensajesAdmin() {
  try {
    const r = await api("GET", "/api/mensajes");
    const lista = Array.isArray(r) ? r : (r.mensajes || []);
    const tbody = document.getElementById("tbody-mensajes");
    if (!lista.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">sin mensajes</td></tr>'; return; }
    tbody.innerHTML = lista.map(m =>
      '<tr>' +
      '<td>' + escHtml(m.id) + '</td>' +
      '<td>' + escHtml(m.remitente || m.de || "") + '</td>' +
      '<td>' + escHtml(m.destinatario || m.para || "") + '</td>' +
      '<td>' + escHtml(m.asunto || "sin asunto") + '</td>' +
      '<td>' + (m.leido ? '<span class="badge badge-activo">si</span>' : '<span class="badge badge-pendiente">no</span>') + '</td>' +
      '<td>' + formatearFecha(m.fecha || m.creado_en) + '</td>' +
      '<td><button class="btn-accion" onclick="mostrarModalVerMensaje(' + m.id + ')">ver</button></td></tr>'
    ).join("");
  } catch(e) { mostrarToast("error: " + e.message, "error"); }
}

// ============================================================
// monitoreo (ws)
// ============================================================
function conectarMonitoreo() {
  if (wsMonitoreo) wsMonitoreo.close();
  const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  try {
    wsMonitoreo = new WebSocket(protocolo + "//" + host + "/ws/admin/monitor");
    wsMonitoreo.onmessage = function(event) {
      try {
        const d = JSON.parse(event.data);
        if (d.tipo === "monitoreo") {
          document.getElementById("mon-pcbots").textContent = d.pcbots_conectados || 0;
          document.getElementById("mon-perfiles").textContent = d.pcs_online || 0;
          document.getElementById("mon-pedidos").textContent = d.comandos_pendientes || 0;
          document.getElementById("mon-comandos").textContent = d.comandos_pendientes || 0;
        }
      } catch(e) {}
    };
    wsMonitoreo.onclose = function() { setTimeout(conectarMonitoreo, 5000); };
    wsMonitoreo.onerror = function() { wsMonitoreo.close(); };
  } catch(e) {
    setTimeout(conectarMonitoreo, 5000);
  }
}

async function cargarMonitoreo() {
  // si no hay ws, intentar via api
  try {
    const r = await api("GET", "/api/admin/monitoreo");
    const d = r.monitoreo || r;
    document.getElementById("mon-pcbots").textContent = d.pcbots_conectados ?? d.pcbots ?? 0;
    document.getElementById("mon-perfiles").textContent = d.perfiles_activos ?? d.pcs_online ?? 0;
    document.getElementById("mon-pedidos").textContent = d.pedidos_pendientes ?? 0;
    document.getElementById("mon-comandos").textContent = d.comandos_pendientes ?? 0;
  } catch(e) {
    // ignorar, el ws ya carga
  }
}

let monSeleccionado = null;

function seleccionarMonitoreo(tipo, card) {
  if (monSeleccionado === tipo) {
    document.querySelectorAll("#tab-content-monitoreo .kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
    document.getElementById("mon-detalle").classList.remove("show");
    document.getElementById("mon-detalle").innerHTML = "";
    monSeleccionado = null;
    return;
  }
  document.querySelectorAll("#tab-content-monitoreo .kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
  card.classList.add("kpi-selected");
  monSeleccionado = tipo;

  const cont = document.getElementById("mon-detalle");
  cont.classList.add("show");
  const labels = {pcbots:"Pcbots Conectados", perfiles:"Perfiles Activos", pedidos:"Pedidos Pendientes", comandos:"Comandos en Cola"};
  cont.innerHTML = '<div class="kpi-detalle-header">' + labels[tipo] + '</div>' +
    '<p class="empty-msg">Detalle en tiempo real proximamente</p>';
}

// ============================================================
// tokenomia
// ============================================================
async function cargarTokenomia() {
  try {
    const r = await api("GET", "/api/admin/tokenomia");
    const d = r.tokenomia || r;
    document.getElementById("tok-oferta").textContent = d.oferta_total ?? "--";
    document.getElementById("tok-quemados").textContent = d.quemados ?? "--";
    document.getElementById("tok-precio").textContent = d.precio_estimado ?? "--";
  } catch(e) {
    // silent
  }
}

let tokSeleccionado = null;

function seleccionarTokenomia(tipo, card) {
  if (tokSeleccionado === tipo) {
    document.querySelectorAll("#tab-content-tokenomia .kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
    document.getElementById("tok-detalle").classList.remove("show");
    document.getElementById("tok-detalle").innerHTML = "";
    tokSeleccionado = null;
    return;
  }
  document.querySelectorAll("#tab-content-tokenomia .kpi-card.kpi-selected").forEach(c => c.classList.remove("kpi-selected"));
  card.classList.add("kpi-selected");
  tokSeleccionado = tipo;

  const cont = document.getElementById("tok-detalle");
  cont.classList.add("show");
  const labels = {oferta:"Oferta Total", quemados:"Tokens Quemados", precio:"Precio Estimado"};
  cont.innerHTML = '<div class="kpi-detalle-header">' + labels[tipo] + '</div>' +
    '<p class="empty-msg">Graficos y detalle proximamente</p>';
}

// ============================================================
// modal generico
// ============================================================
function mostrarModal(titulo, cuerpoHTML, callback) {
  document.getElementById("modal-titulo").textContent = titulo;
  document.getElementById("modal-cuerpo").innerHTML = cuerpoHTML;
  const confirmBtn = document.getElementById("modal-btn-confirmar");
  if (callback) {
    confirmBtn.style.display = "inline-block";
    modalCallback = callback;
  } else {
    confirmBtn.style.display = "none";
    modalCallback = null;
  }
  document.getElementById("modal-accion").classList.add("show");
}

function cerrarModal() {
  document.getElementById("modal-accion").classList.remove("show");
  modalCallback = null;
}

function confirmarModal() {
  if (typeof modalCallback === "function") {
    modalCallback();
  }
  cerrarModal();
}

// ============================================================
// modales CRUD: usuarios
// ============================================================
function mostrarModalEditarUsuario(id) {
  const u = usuariosCache.find(x => x.id == id);
  if (!u) return;
  const html = '<label>Email</label><input type="email" id="modal-email" value="' + escHtml(u.email) + '">' +
    '<label>Username</label><input id="modal-username" value="' + escHtml(u.username || "") + '">' +
    '<label>Rol</label><select id="modal-rol">' +
    '<option value="usuario" ' + (u.rol === "usuario" ? "selected" : "") + '>usuario</option>' +
    '<option value="granjero" ' + (u.rol === "granjero" ? "selected" : "") + '>granjero</option>' +
    '<option value="moderador" ' + (u.rol === "moderador" ? "selected" : "") + '>moderador</option>' +
    '<option value="admin" ' + (u.rol === "admin" ? "selected" : "") + '>admin</option>' +
    (rolActual === "dueno" ? '<option value="dueno" ' + (u.rol === "dueno" ? "selected" : "") + '>dueno</option>' : "") +
    '</select>' +
    '<label>Pcbot ID</label><input id="modal-pcbot" value="' + escHtml(u.pcbot_id || "") + '">' +
    '<label>Activo</label><select id="modal-activo"><option value="1" ' + (u.activo == 1 ? "selected" : "") + '>si</option><option value="0" ' + (u.activo == 0 ? "selected" : "") + '>no</option></select>' +
    '<label>Nivel Confianza</label><input id="modal-confianza" value="' + escHtml(u.nivel_fiabilidad || "bronce") + '">';
  mostrarModal("Editar Usuario #" + id, html, async () => {
    try {
      const datos = {
        email: document.getElementById("modal-email").value,
        username: document.getElementById("modal-username").value,
        rol: document.getElementById("modal-rol").value,
        pcbot_id: document.getElementById("modal-pcbot").value || null,
        activo: parseInt(document.getElementById("modal-activo").value),
        nivel_fiabilidad: document.getElementById("modal-confianza").value
      };
      await api("PUT", "/api/admin/usuarios/" + id, datos);
      mostrarToast("usuario #" + id + " actualizado", "success");
      listarUsuarios();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalEliminarUsuario(id) {
  const u = usuariosCache.find(x => x.id == id);
  const html = '<div class="modal-mensaje">¿esta seguro de eliminar permanentemente al usuario <strong>' + escHtml(u ? u.email : "") + '</strong>? se eliminaran tambien sus sesiones, wallet y perfiles.</div>';
  mostrarModal("Eliminar Usuario #" + id, html, async () => {
    try {
      await api("DELETE", "/api/admin/usuarios/" + id);
      mostrarToast("usuario #" + id + " eliminado", "success");
      listarUsuarios();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalCrearUsuario() {
  const html = '<label>Email</label><input type="email" id="modal-email">' +
    '<label>Password</label><input type="password" id="modal-password">' +
    '<label>Username</label><input id="modal-username">' +
    '<label>Rol</label><select id="modal-rol">' +
    '<option value="usuario">usuario</option><option value="granjero">granjero</option>' +
    '<option value="moderador">moderador</option>' +
    (rolActual === "dueno" ? '<option value="admin">admin</option>' : '<option value="admin" disabled>admin (solo dueno)</option>') +
    '</select>';
  mostrarModal("Crear Nuevo Usuario", html, async () => {
    try {
      await api("POST", "/api/admin/usuarios", {
        email: document.getElementById("modal-email").value,
        password: document.getElementById("modal-password").value,
        username: document.getElementById("modal-username").value,
        rol: document.getElementById("modal-rol").value
      });
      mostrarToast("usuario creado", "success");
      listarUsuarios();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

// ============================================================
// modales CRUD: perfiles
// ============================================================
function mostrarModalCrearPerfil(usuarioId) {
  const html = '<label>Nombre del Perfil</label><input id="modal-nombre-perfil" placeholder="ej: pc-oficina-1">' +
    '<label>Tipo</label><select id="modal-tipo-perfil"><option value="local">local</option><option value="remoto">remoto</option><option value="vps">vps</option></select>';
  mostrarModal("Crear Perfil para Usuario #" + usuarioId, html, async () => {
    try {
      await api("POST", "/api/admin/perfiles", {
        usuario_id: usuarioId,
        nombre_perfil: document.getElementById("modal-nombre-perfil").value,
        tipo: document.getElementById("modal-tipo-perfil").value
      });
      mostrarToast("perfil creado", "success");
      listarPerfiles();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalEditarPerfil(id) {
  const p = perfilesCache.find(x => x.id == id);
  if (!p) return;
  const html = '<label>Nombre</label><input id="modal-nombre" value="' + escHtml(p.nombre_perfil || "") + '">' +
    '<label>Estado</label><select id="modal-estado"><option value="activo" ' + (p.estado === "activo" ? "selected" : "") + '>activo</option><option value="inactivo" ' + (p.estado === "inactivo" ? "selected" : "") + '>inactivo</option><option value="desconectado" ' + (p.estado === "desconectado" ? "selected" : "") + '>desconectado</option></select>' +
    '<label>IP WAN</label><input id="modal-ip" value="' + escHtml(p.ip_wan || "") + '">';
  mostrarModal("Editar Perfil #" + id, html, async () => {
    try {
      await api("PUT", "/api/admin/perfiles/" + id, {
        nombre: document.getElementById("modal-nombre").value,
        estado: document.getElementById("modal-estado").value,
        ip_wan: document.getElementById("modal-ip").value
      });
      mostrarToast("perfil #" + id + " actualizado", "success");
      listarPerfiles();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalEliminarPerfil(id) {
  const html = '<div class="modal-mensaje">¿eliminar perfil #' + id + '?</div>';
  mostrarModal("Eliminar Perfil #" + id, html, async () => {
    try {
      await api("DELETE", "/api/admin/perfiles/" + id);
      mostrarToast("perfil #" + id + " eliminado", "success");
      listarPerfiles();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalEditarPc(id) {
  const html = '<label>Modo</label><select id="modal-modo"><option value="conectado">conectado</option><option value="desconectado">desconectado</option><option value="mantenimiento">mantenimiento</option></select>';
  mostrarModal("Editar PC #" + id, html, async () => {
    try {
      await api("PUT", "/api/admin/pcs/" + id, { modo: document.getElementById("modal-modo").value });
      mostrarToast("pc #" + id + " actualizada", "success");
      listarPcs();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

function mostrarModalVerMensaje(id) {
  // intentar obtener detalle del mensaje
  const html = '<div class="modal-mensaje">detalle del mensaje #' + id + ' proximamente</div>';
  mostrarModal("Mensaje #" + id, html, null);
}

function mostrarModalEnviarMensaje() {
  const html = '<label>Destinatario Email</label><input id="modal-destino" placeholder="email@ejemplo.com">' +
    '<label>Asunto</label><input id="modal-asunto" placeholder="asunto">' +
    '<label>Mensaje</label><textarea id="modal-contenido" rows="3"></textarea>';
  mostrarModal("Enviar Mensaje", html, async () => {
    try {
      await api("POST", "/api/mensajes", {
        destino: document.getElementById("modal-destino").value,
        asunto: document.getElementById("modal-asunto").value,
        contenido: document.getElementById("modal-contenido").value
      });
      mostrarToast("mensaje enviado", "success");
      listarMensajesAdmin();
    } catch(e) { mostrarToast("error: " + e.message, "error"); }
  });
}

// ============================================================
// cierre de sesion
// ============================================================
async function cerrarSesion() {
  try {
    await api("POST", "/api/logout");
  } catch(e) {}
  localStorage.removeItem("token");
  localStorage.removeItem("usuario_email");
  localStorage.removeItem("usuario_rol");
  window.location.href = "/publico/login.html";
}

// ============================================================
// roles y permisos
// ============================================================
function aplicarRestriccionesPorRol() {
  const esDueno = (rolActual === "dueno");
  const esAdmin = (rolActual === "admin");
  const esModerador = (rolActual === "moderador");

  // mostrar elementos segun rol
  document.querySelectorAll(".rol-dueno-only").forEach(el => { el.style.display = esDueno ? "" : "none"; });
  document.querySelectorAll(".rol-admin-only").forEach(el => { el.style.display = esDueno || esAdmin ? "" : "none"; });
  document.querySelectorAll(".rol-moderador-only").forEach(el => { el.style.display = esModerador ? "" : "none"; });

  // ocultar pestañas completas segun rol
  const tabsOcultas = [];
  if (esModerador) {
    tabsOcultas.push("sesiones", "pcs", "monitoreo", "tokenomia", "proyecciones", "seguridad");
  }

  tabsOcultas.forEach(tab => {
    const nav = document.getElementById("nav-" + tab);
    if (nav) nav.style.display = "none";
  });
}

// ============================================================
// init
// ============================================================
(function init() {
  const p = new URLSearchParams(window.location.search);
  const tParam = p.get("token");
  if (tParam) {
    token = tParam;
    localStorage.setItem("token", token);
  } else {
    token = localStorage.getItem("token") || "";
  }
  const emailStorage = localStorage.getItem("usuario_email");
  const rolStorage = localStorage.getItem("usuario_rol");
  if (emailStorage) {
    usuarioActual = emailStorage;
    rolActual = rolStorage || "";
    document.getElementById("usuario_email").textContent = emailStorage;
  }
  // validar rol: solo admin, dueno o moderador
  if (rolStorage && rolStorage !== "admin" && rolStorage !== "dueno" && rolStorage !== "moderador") {
    window.location.href = "/publico/dashboard_publico.html?token=" + encodeURIComponent(token);
    return;
  }
  if (!token) {
    window.location.href = "/publico/login.html";
    return;
  }
  aplicarRestriccionesPorRol();
  cargarKPI();
  conectarMonitoreo();
  // cargar monitoreo via api como fallback
  setTimeout(() => cargarMonitoreo(), 1000);
  // cargar tokenomia
  setTimeout(() => cargarTokenomia(), 1500);
})();