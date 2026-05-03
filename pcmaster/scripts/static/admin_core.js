// admin_core.js - utilidades compartidas del dashboard de administracion v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
var roxy = roxy || {};

roxy.token = document.cookie.replace(/(?:(?:^|.*;\s*)token\s*=\s*([^;]*).*$)|^.*$/, "$1") || null;

// ---------------------------------------------------------------------------
// init - inicializa el dashboard, verifica sesion, bindea navegacion
// ---------------------------------------------------------------------------
roxy.init = async function () {
  if (!roxy.token) { window.location.href = "/login"; return; }
  try {
    var d = await roxy.api_call("GET", "/api/dashboard/perfil");
    if (d.exito && d.usuario) {
      document.getElementById("usuario_email").textContent = d.usuario.email;
      roxy.rol = d.usuario.rol;
    } else { window.location.href = "/login"; return; }
  } catch (e) { window.location.href = "/login"; return; }

  document.querySelectorAll(".sidebar nav a[data-tab]").forEach(function (a) {
    a.addEventListener("click", function () { roxy.navegar(this.getAttribute("data-tab")); });
  });
  var overlay = document.getElementById("modal_overlay");
  if (overlay) overlay.addEventListener("click", function (e) { if (e.target === overlay) roxy.cerrar_modal(); });
  roxy.navegar("kpi");
  if (roxy.rol === "admin") roxy.iniciar_poller_mensajes();
};

// ---------------------------------------------------------------------------
// api_call - llamada generica a la api con token bearer
// ---------------------------------------------------------------------------
roxy.api_call = async function (metodo, url, body) {
  var opts = { method: metodo, headers: { "Content-Type": "application/json" } };
  if (roxy.token) opts.headers["Authorization"] = "Bearer " + roxy.token;
  if (body && (metodo === "POST" || metodo === "PUT" || metodo === "PATCH")) opts.body = JSON.stringify(body);
  var resp = await fetch(url, opts);
  if (resp.status === 401) { roxy.cerrar_sesion(); throw new Error("sesion expirada"); }
  if (!resp.ok) {
    var errText = await resp.text();
    var errJson = null;
    try { errJson = JSON.parse(errText); } catch (e2) {}
    throw new Error((errJson && errJson.detail) || ("error " + resp.status));
  }
  return await resp.json();
};

// ---------------------------------------------------------------------------
// navegar - cambia entre paneles del dashboard
// ---------------------------------------------------------------------------
roxy.navegar = function (tab) {
  document.querySelectorAll(".sidebar nav a[data-tab]").forEach(function (a) {
    a.classList.toggle("activo", a.getAttribute("data-tab") === tab);
  });
  document.querySelectorAll(".tab-content").forEach(function (p) { p.classList.remove("activo"); });
  var target = document.getElementById("tab_" + tab);
  if (target) target.classList.add("activo");
  var titulo = document.getElementById("panel_titulo");
  if (titulo) titulo.textContent = "panel " + tab.replace(/_/g, " ");

  switch (tab) {
    case "kpi": roxy.cargar_kpi(); break;
    case "usuarios": roxy.cargar_usuarios(); break;
    case "perfiles": roxy.cargar_perfiles(); break;
    case "pcs": roxy.cargar_pcs(); break;
    case "sesiones": roxy.cargar_sesiones(); break;
    case "retiros": roxy.cargar_retiros(); break;
    case "mensajes": roxy.cargar_mensajes(); break;
    case "tokenomia": roxy.cargar_tokenomia(); break;
    case "proyecciones": roxy.cargar_proyecciones(); break;
    case "happy_hour": roxy.cargar_happy_hour(); break;
    case "seguridad": roxy.cargar_seguridad(); break;
  }
};

// ---------------------------------------------------------------------------
// modal - abrir y cerrar ventana modal
// ---------------------------------------------------------------------------
roxy.abrir_modal = function (titulo, contenido) {
  var overlay = document.getElementById("modal_overlay");
  var modal = document.getElementById("modal_contenido");
  if (!overlay || !modal) return;
  modal.innerHTML = "<button class='close' onclick='roxy.cerrar_modal()'>x</button><h2>" + roxy.escape_html(titulo) + "</h2>" + contenido;
  overlay.classList.add("activo");
};
roxy.cerrar_modal = function () {
  var overlay = document.getElementById("modal_overlay");
  if (overlay) overlay.classList.remove("activo");
};

// ---------------------------------------------------------------------------
// toast - notificaciones flotantes
// ---------------------------------------------------------------------------
roxy.toast = function (mensaje, clase) {
  clase = clase || "toast-info";
  var container = document.getElementById("toast_container");
  if (!container) return;
  var el = document.createElement("div");
  el.className = "toast " + clase;
  el.textContent = mensaje;
  container.appendChild(el);
  setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 4000);
};

// ---------------------------------------------------------------------------
// cerrar_sesion
// ---------------------------------------------------------------------------
roxy.cerrar_sesion = async function () {
  try { await roxy.api_call("POST", "/api/auth/logout"); } catch (e) {}
  document.cookie = "token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
  window.location.href = "/login";
};

// ---------------------------------------------------------------------------
// confirmar - wrapper de confirm() nativo
// ---------------------------------------------------------------------------
roxy.confirmar = function (msg, cb) { if (confirm(msg)) cb(); };

// ---------------------------------------------------------------------------
// poller de mensajes no leidos (cada 30s)
// ---------------------------------------------------------------------------
roxy.iniciar_poller_mensajes = function () {
  if (roxy._poller) clearInterval(roxy._poller);
  roxy._poller = setInterval(async function () {
    try {
      var d = await roxy.api_call("GET", "/api/mensajes/no_leidos");
      var badge = document.getElementById("msg_badge");
      if (badge) { badge.textContent = d.count || "0"; badge.style.display = d.count > 0 ? "inline-block" : "none"; }
    } catch (e) {}
  }, 30000);
};

// ---------------------------------------------------------------------------
// helpers: formato de fecha, escape html, render de tabla
// ---------------------------------------------------------------------------
roxy.format_fecha = function (str) {
  if (!str) return "-";
  try { var d = new Date(str + "Z"); return d.toLocaleString("es-PE"); } catch (e) { return str; }
};

roxy._escape_map = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "\"": "&quot;"
};

roxy.escape_html = function (str) {
  if (!str) return "";
  var m = roxy._escape_map;
  return String(str).replace(/[&<>"]/g, function (c) { return m[c]; });
};

roxy.render_tabla = function (columnas, filas, acciones) {
  var h = "<div style='overflow-x:auto'><table><thead><tr>";
  columnas.forEach(function (c) { h += "<th>" + roxy.escape_html(String(c)) + "</th>"; });
  if (acciones) h += "<th style='width:120px'>acciones</th>";
  h += "</tr></thead><tbody>";
  filas.forEach(function (f) {
    h += "<tr>";
    columnas.forEach(function (c) {
      h += "<td>" + (f[c] !== undefined ? roxy.escape_html(String(f[c])) : "-") + "</td>";
    });
    if (acciones) {
      h += "<td>" + acciones.map(function (a) {
        return "<button class='btn btn-sm " + (a.clase || "btn-outline") + "' onclick='" +
          a.onclick.replace(/{id}/g, roxy.escape_html(String(f.id || ""))) + "'>" +
          roxy.escape_html(a.texto) + "</button>";
      }).join(" ") + "</td>";
    }
    h += "</tr>";
  });
  h += "</tbody></table></div>";
  return h;
};
