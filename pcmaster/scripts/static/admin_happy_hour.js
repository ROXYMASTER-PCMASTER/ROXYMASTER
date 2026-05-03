// admin_happy_hour.js - panel de happy hour v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_happy_hour = async function () {
  var container = document.getElementById("tab_happy_hour");
  if (!container) return;
  container.innerHTML = "<p>cargando...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/happy_hour/historial");
    var html = "<h3>activar happy hour</h3>";
    html +=
      "<div class='form-group'>" +
      "<label>multiplicador:</label>" +
      "<input id='hh_mult' value='2.0' type='number' step='0.1'>" +
      "</div>" +
      "<div class='form-group'>" +
      "<label>fecha inicio:</label>" +
      "<input id='hh_ini' type='datetime-local'>" +
      "</div>" +
      "<div class='form-group'>" +
      "<label>fecha fin:</label>" +
      "<input id='hh_fin' type='datetime-local'>" +
      "</div>" +
      "<button class='btn' onclick='roxy.activar_hh()'>activar</button>" +
      "<button class='btn btn-outline' onclick='roxy.desactivar_hh()'>desactivar</button>";
    var columnas = [
      "id",
      "multiplicador",
      "fecha_inicio",
      "fecha_fin",
      "activo",
    ];
    var filas = (d.historial || []).map(function (h) {
      return [h.id, h.multiplicador, h.fecha_inicio || "-", h.fecha_fin || "-", h.activo ? "si" : "no"];
    });
    html += "<h3>historial</h3>" + roxy.render_tabla(columnas, filas);
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.activar_hh = async function () {
  try {
    await roxy.api_call("POST", "/api/admin/happy_hour/activar", {
      multiplicador: parseFloat(document.getElementById("hh_mult").value) || 2.0,
      fecha_inicio: document.getElementById("hh_ini").value,
      fecha_fin: document.getElementById("hh_fin").value,
    });
    roxy.toast("happy hour activado", "toast-success");
    roxy.cargar_happy_hour();
    roxy.cargar_kpi();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};

roxy.desactivar_hh = async function () {
  try {
    await roxy.api_call("POST", "/api/admin/happy_hour/desactivar");
    roxy.toast("happy hour desactivado", "toast-success");
    roxy.cargar_happy_hour();
    roxy.cargar_kpi();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};