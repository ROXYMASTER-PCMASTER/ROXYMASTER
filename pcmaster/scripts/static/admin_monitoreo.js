// admin_monitoreo.js - panel de monitoreo interno v8.3
// utf-8 sin bom, nombres en minusculas
"use strict";
roxy.cargar_monitoreo = async function () {
  var container = document.getElementById("tab_monitoreo");
  if (!container) return;
  try {
    var res = await roxy.api_call("GET", "/api/monitoreo/resumen");
    var comp = await roxy.api_call("GET", "/api/monitoreo/componentes");
    var html =
      "<div class='kpi-grid'>" +
      roxy.tarjeta_kpi("pcbots conectados", res.pcbots.conectados, "total: " + res.pcbots.total, "#58a6ff") +
      roxy.tarjeta_kpi("comandos pendientes", res.comandos.pendientes, "completados: " + res.comandos.completados, "#d29922") +
      roxy.tarjeta_kpi("pedidos pendientes", res.pedidos.pendientes, "total: " + res.pedidos.total, "#3fb950") +
      roxy.tarjeta_kpi("jarvis", res.jarvis.activo ? "activo" : "inactivo", "modo: " + res.jarvis.modo, res.jarvis.activo ? "#3fb950" : "#f85149") +
      "</div>" +
      "<div class='card'><h2>estado de componentes</h2><table><thead><tr><th>componente</th><th>estado</th><th>detalle</th></tr></thead><tbody>";

    for (var c in comp.componentes) {
      var ok = comp.componentes[c].ok;
      html += "<tr>" +
        "<td>" + c + "</td>" +
        "<td style='color:" + (ok ? "#3fb950" : "#f85149") + "'>" + (ok ? "ok" : "fallo") + "</td>" +
        "<td>" + comp.componentes[c].detalle + "</td>" +
        "</tr>";
    }
    html += "</tbody></table></div>";

    // metricas
    var met = await roxy.api_call("GET", "/api/monitoreo/metricas?horas=24");
    if (met.comandos_por_hora && met.comandos_por_hora.length > 0) {
      html += "<div class='card'><h2>comandos por hora (ultimas 24h)</h2><table><thead><tr><th>hora</th><th>total</th><th>completados</th></tr></thead><tbody>";
      met.comandos_por_hora.slice(0, 12).forEach(function (h) {
        html += "<tr><td>" + h.hora + "</td><td>" + h.total_cmds + "</td><td>" + (h.completados || 0) + "</td></tr>";
      });
      html += "</tbody></table></div>";
    }

    html += "<div class='card'><h2>logs recientes</h2><div id='monitoreo_logs'><div class='loading'></div></div></div>";
    container.innerHTML = html;

    // cargar logs via js aparte
    roxy.cargar_logs_monitoreo();
  } catch (e) {
    container.innerHTML = "<div class='card'><h2>error al cargar monitoreo</h2><p>" + e.message + "</p></div>";
  }
};

roxy.cargar_logs_monitoreo = async function () {
  var cont = document.getElementById("monitoreo_logs");
  if (!cont) return;
  try {
    var logs = await roxy.api_call("GET", "/api/monitoreo/logs?limite=20");
    var html = "<table><thead><tr><th>nivel</th><th>mensaje</th><th>origen</th><th>timestamp</th></tr></thead><tbody>";
    logs.logs.forEach(function (l) {
      var color = l.nivel === "error" ? "#f85149" : l.nivel === "warn" ? "#d29922" : "#3fb950";
      html += "<tr>" +
        "<td style='color:" + color + "'>" + l.nivel + "</td>" +
        "<td>" + (l.mensaje || "").substring(0, 80) + "</td>" +
        "<td>" + l.origen + "</td>" +
        "<td>" + l.timestamp + "</td>" +
        "</tr>";
    });
    html += "</tbody></table>";
    cont.innerHTML = html;
  } catch (e) {
    cont.innerHTML = "<p style='color:#f85149'>error al cargar logs: " + e.message + "</p>";
  }
};