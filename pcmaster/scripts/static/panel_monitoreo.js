"use strict";
/* panel_monitoreo.js - modulo monitoreo y estado */
/* version 1.0 - todo en minusculas */

(function () {

  roxy.onTab("monitoreo", function () {
    var contenedor = document.getElementById("tab_monitoreo");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="card"><div class="card-header">estado del sistema</div>'
      + '<div class="card-body"><div id="monitoreo_estado"></div></div></div>'
      + '<div class="card"><div class="card-header">ultimos errores</div>'
      + '<div class="card-body"><div id="monitoreo_errores"></div></div></div>';
    cargarEstado();
    cargarErrores();
    // auto-refresh cada 30 segundos
    if (window._monInterval) { clearInterval(window._monInterval); }
    window._monInterval = setInterval(function () {
      cargarEstado();
      cargarErrores();
    }, 30000);
  });

  function cargarEstado() {
    roxy.api("/monitoreo/estado")
      .then(function (data) {
        var el = document.getElementById("monitoreo_estado");
        if (!el) { return; }
        var items = [
          { label: "servidor", val: data.servidor || data.status || "desconocido" },
          { label: "uptime", val: data.uptime || data.tiempo_activo || "-" },
          { label: "cpu", val: data.cpu || data.cpu_uso || "-" + "%" },
          { label: "memoria", val: data.memoria || data.ram_uso || "-" + "%" },
          { label: "conexiones ws", val: data.ws_conexiones || data.websockets || "0" },
          { label: "version", val: data.version || data.app_version || "-" },
        ];
        el.innerHTML = items.map(function (item) {
          var ok = item.val === "ok" || item.val === "saludable" || item.val === "online";
          return '<div class="var-row">'
            + '<span class="var-label">' + roxy.escaparHtml(item.label) + '</span>'
            + '<span class="var-input">'
            + (ok ? '<span class="text-success">' : "")
            + roxy.escaparHtml(String(item.val))
            + (ok ? '</span>' : "")
            + '</span></div>';
        }).join("");
      })
      .catch(function (err) {
        var el = document.getElementById("monitoreo_estado");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  }

  function cargarErrores() {
    roxy.api("/monitoreo/errores")
      .then(function (data) {
        var el = document.getElementById("monitoreo_errores");
        if (!el) { return; }
        var errores = data.errores || data.logs || data || [];
        if (!Array.isArray(errores)) { errores = []; }
        if (!errores.length) {
          el.innerHTML = '<div class="text-success p-3">sin errores recientes</div>';
          return;
        }
        el.innerHTML = errores.slice(0, 20).map(function (e) {
          return '<div class="evento-row">'
            + '<span class="ev-tipo ev-critico">error</span>'
            + roxy.escaparHtml(e.mensaje || e.message || e.error || "")
            + '<span class="float-end text-muted small">' + roxy.escaparHtml(e.fecha || e.timestamp || "") + '</span>'
            + '</div>';
        }).join("");
      })
      .catch(function () {
        var el = document.getElementById("monitoreo_errores");
        if (el) { el.innerHTML = '<div class="loading-placeholder">sin errores</div>'; }
      });
  }

})();