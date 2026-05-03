"use strict";
/* roxymaster.js - modulo core administracion */
/* version 1.0 - todo en minusculas */

var roxy = (function () {
  var _token = null;
  var _usuario = null;
  var _tab_actual = "kpi";
  var _listeners = {};
  var _sesion_verificada = false;

  function _api(path, options) {
    options = options || {};
    var headers = { "content-type": "application/json" };
    if (_token) { headers["x-auth-token"] = _token; }
    var fetchOpts = {
      method: options.method || "GET",
      headers: headers,
    };
    if (options.body) { fetchOpts.body = JSON.stringify(options.body); }
    return fetch(path, fetchOpts)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { throw new Error(data.error); }
        if (data.detail) { throw new Error(data.detail); }
        return data;
      });
  }

  function api(path, options) { return _api(path, options); }

  function toast(mensaje, tipo) {
    tipo = tipo || "info";
    var container = document.getElementById("toast_container");
    if (!container) { return; }
    var el = document.createElement("div");
    el.className = "toast align-items-center text-bg-dark border-0 show";
    el.innerHTML = '<div class="d-flex"><div class="toast-body">'
      + mensaje
      + '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    container.appendChild(el);
    var bsToast = new bootstrap.Toast(el, { autohide: true, delay: 3500 });
    bsToast.show();
    el.addEventListener("hidden.bs.toast", function () { el.remove(); });
  }

  function errorToast(err) {
    var msg = (err && err.message) ? err.message : "error desconocido";
    toast(msg, "error");
  }

  function modal(titulo, html) {
    var overlay = document.getElementById("modal_overlay");
    var contenido = document.getElementById("modal_contenido");
    if (!overlay || !contenido) { return; }
    contenido.innerHTML = '<div class="modal-header"><h5 class="modal-title">'
      + titulo
      + '</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
      + '<div class="modal-body">' + html + '</div>';
    var bsModal = new bootstrap.Modal(overlay);
    bsModal.show();
  }

  function modalCerrar() {
    var overlay = document.getElementById("modal_overlay");
    if (overlay) {
      var bsModal = bootstrap.Modal.getInstance(overlay);
      if (bsModal) { bsModal.hide(); }
    }
  }

  function cargando(id) {
    var el = document.getElementById(id);
    if (el) { el.innerHTML = '<div class="loading-placeholder">cargando</div>'; }
  }

  var _amp = String.fromCharCode(38);

  function escaparHtml(str) {
    if (!str) { return ""; }
    return String(str).replace(/[&<>"']/g, function (c) {
      if (c === "&") { return _amp + "amp;"; }
      if (c === "<") { return _amp + "lt;"; }
      if (c === ">") { return _amp + "gt;"; }
      if (c === '"') { return _amp + "quot;"; }
      if (c === "'") { return _amp + "#039;"; }
      return c;
    });
  }

  function init() {
    _token = localStorage.getItem("admin_token");
    if (!_token) { mostrarLogin(); return; }
    verificarSesion();
    cargarMsgBadge();
  }

  function mostrarLogin() {
    if (_sesion_verificada) { return; }
    var main = document.querySelector(".main-wrapper");
    if (!main) { return; }
    document.getElementById("preloader").style.display = "none";
    main.innerHTML = ''
      + '<div class="row justify-content-center mt-5">'
      + '<div class="col-md-4">'
      + '<div class="card"><div class="card-body p-4">'
      + '<h3 class="text-center mb-4" style="color:var(--accent)">roxymaster v8.3</h3>'
      + '<div class="mb-3">'
      + '<label class="form-label">email</label>'
      + '<input type="email" class="form-control" id="login_email" placeholder="admin@email.com">'
      + '</div>'
      + '<div class="mb-3">'
      + '<label class="form-label">contrase;qa</label>'
      + '<input type="password" class="form-control" id="login_pass" placeholder="contrase;qa">'
      + '</div>'
      + '<button class="btn btn-primary w-100" onclick="roxy.login()">ingresar</button>'
      + '<div id="login_error" class="mt-2 text-danger small" style="display:none"></div>'
      + '</div></div></div></div>';
    document.getElementById("login_pass").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { login(); }
    });
  }

  function login() {
    var email = document.getElementById("login_email").value.trim();
    var pass = document.getElementById("login_pass").value;
    var errorEl = document.getElementById("login_error");
    if (!email || !pass) {
      errorEl.textContent = "completa email y contrase;qa";
      errorEl.style.display = "block";
      return;
    }
    fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: email, password: pass }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.token) {
          _token = data.token;
          _usuario = data.usuario || null;
          localStorage.setItem("admin_token", _token);
          location.reload();
        } else {
          errorEl.textContent = data.error || data.detail || "credenciales invalidas";
          errorEl.style.display = "block";
        }
      })
      .catch(function (err) {
        errorEl.textContent = "error de conexion: " + err.message;
        errorEl.style.display = "block";
      });
  }

  function cerrarSesion() {
    _token = null;
    localStorage.removeItem("admin_token");
    location.reload();
  }

  function verificarSesion() {
    _api("/verify")
      .then(function (data) {
        if (data.exito) {
          _usuario = data.usuario || data.sesion || null;
          _sesion_verificada = true;
          document.getElementById("preloader").style.display = "none";
          mostrarInfoUsuario();
          navegar(_tab_actual);
        } else {
          _token = null;
          localStorage.removeItem("admin_token");
          mostrarLogin();
        }
      })
      .catch(function () {
        _token = null;
        localStorage.removeItem("admin_token");
        _sesion_verificada = false;
        mostrarLogin();
      });
  }

  function mostrarInfoUsuario() {
    var el = document.getElementById("usuario_email");
    if (el && _usuario) {
      el.textContent = _usuario.email || _usuario.usuario_id || "admin";
    }
  }

  function navegar(tab) {
    _tab_actual = tab;
    document.querySelectorAll(".sidebar nav a").forEach(function (a) {
      a.classList.toggle("activo", a.getAttribute("data-tab") === tab);
    });
    var titulo = document.getElementById("panel_titulo");
    if (titulo) {
      var nombres = {
        kpi: "panel kpi",
        usuarios: "usuarios",
        perfiles: "perfiles",
        pcs: "pcbots",
        sesiones: "sesiones",
        retiros: "retiros",
        mensajes: "mensajes",
        monitoreo: "monitoreo",
        tokenomia: "tokenomia",
        proyecciones: "proyecciones",
        happy_hour: "happy hour",
        seguridad: "seguridad",
      };
      titulo.textContent = nombres[tab] || tab;
    }
    document.querySelectorAll(".tab-content").forEach(function (el) {
      el.classList.remove("activo");
    });
    var target = document.getElementById("tab_" + tab);
    if (target) { target.classList.add("activo"); }
    if (_listeners[tab]) { _listeners[tab](); }
  }

  function onTab(tab, fn) {
    _listeners[tab] = fn;
  }

  function cargarMsgBadge() {
    _api("/mensajes/historial?limit=1")
      .then(function () {
        var badge = document.getElementById("msg_badge");
        if (!badge) { return; }
        _api("/mensajes/no-leidos")
          .then(function (d) {
            var count = d.total || d.cantidad || 0;
            badge.textContent = count;
            badge.style.display = count > 0 ? "inline" : "none";
          })
          .catch(function () { badge.textContent = "0"; });
      })
      .catch(function () {});
  }

  function toggleSidebar() {
    var sidebar = document.querySelector(".sidebar");
    var overlay = document.querySelector(".sidebar-overlay");
    if (sidebar) {
      sidebar.classList.toggle("active");
      if (overlay) { overlay.classList.toggle("active"); }
    }
  }

  return {
    init: init,
    login: login,
    cerrarSesion: cerrarSesion,
    navegar: navegar,
    onTab: onTab,
    api: api,
    toast: toast,
    errorToast: errorToast,
    modal: modal,
    modalCerrar: modalCerrar,
    cargando: cargando,
    escaparHtml: escaparHtml,
    toggleSidebar: toggleSidebar,
    getToken: function () { return _token; },
    getUsuario: function () { return _usuario; },
  };
})();