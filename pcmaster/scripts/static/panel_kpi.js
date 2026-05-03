"use strict";
/* panel_kpi.js - modulo de indicadores */
/* version 1.0 - todo en minusculas */

(function () {

  roxy.onTab("kpi", function () {
    var contenedor = document.getElementById("tab_kpi");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="kpi-grid" id="kpi_grid"></div>'
      + '<div class="card"><div class="card-header">grafico de actividad</div>'
      + '<div class="card-body"><canvas id="kpi_chart" height="200"></canvas></div></div>'
      + '<div class="card"><div class="card-header">ultimos eventos</div>'
      + '<div class="card-body"><div id="kpi_eventos"></div></div></div>';
    cargarKpis();
    cargarEventos();
  });

  function cargarKpis() {
    roxy.api("/kpi/resumen")
      .then(function (data) {
        var grid = document.getElementById("kpi_grid");
        if (!grid) { return; }
        grid.innerHTML = "";
        var items = [
          { label: "usuarios activos", valor: data.usuarios_activos || data.total_usuarios || 0 },
          { label: "pcbots online", valor: data.pcs_online || data.pcs_activas || 0 },
          { label: "sesiones hoy", valor: data.sesiones_hoy || 0 },
          { label: "retiros pendientes", valor: data.retiros_pendientes || 0, sub: data.monto_pendiente ? "$" + data.monto_pendiente : "" },
          { label: "mensajes no leidos", valor: data.mensajes_no_leidos || 0 },
          { label: "saldo total", valor: data.saldo_total || 0 },
        ];
        items.forEach(function (item) {
          grid.innerHTML += '<div class="kpi-card">'
            + '<div class="kpi-label">' + roxy.escaparHtml(item.label) + '</div>'
            + '<div class="kpi-valor">' + item.valor + '</div>'
            + (item.sub ? '<div class="kpi-sub">' + roxy.escaparHtml(item.sub) + '</div>' : "")
            + '</div>';
        });
        renderizarChart(data);
      })
      .catch(function (err) {
        roxy.errorToast(err);
      });
  }

  function renderizarChart(data) {
    var canvas = document.getElementById("kpi_chart");
    if (!canvas) { return; }
    if (window._kpiChart) {
      window._kpiChart.destroy();
    }
    var ctx = canvas.getContext("2d");
    if (typeof Chart === "undefined") { return; }
    window._kpiChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: ["lun", "mar", "mie", "jue", "vie", "sab", "dom"],
        datasets: [{
          label: "actividad",
          data: data.semanal || [0, 0, 0, 0, 0, 0, 0],
          borderColor: "#58a6ff",
          backgroundColor: "rgba(88,166,255,0.1)",
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
          y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
        },
      },
    });
  }

  function cargarEventos() {
    roxy.api("/seguridad/eventos?limit=10")
      .then(function (data) {
        var el = document.getElementById("kpi_eventos");
        if (!el) { return; }
        var eventos = data.eventos || data || [];
        if (!eventos.length) {
          el.innerHTML = '<div class="loading-placeholder">sin eventos recientes</div>';
          return;
        }
        el.innerHTML = eventos.map(function (e) {
          var tipo = (e.tipo || e.level || "info").toLowerCase();
          var clase = "ev-info";
          if (tipo === "critico" || tipo === "critical") { clase = "ev-critico"; }
          else if (tipo === "alerta" || tipo === "warning") { clase = "ev-alerta"; }
          return '<div class="evento-row">'
            + '<span class="ev-tipo ' + clase + '">' + roxy.escaparHtml(tipo) + '</span>'
            + roxy.escaparHtml(e.mensaje || e.descripcion || e.message || "")
            + '<span class="float-end text-muted small">' + roxy.escaparHtml(e.fecha || e.timestamp || "") + '</span>'
            + '</div>';
        }).join("");
      })
      .catch(function (err) {
        var el = document.getElementById("kpi_eventos");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error al cargar eventos</div>'; }
      });
  }

})();