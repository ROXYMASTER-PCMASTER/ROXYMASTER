// admin_seguridad.js - panel de seguridad y logs v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_seguridad = async function () {
  var container = document.getElementById("tab_seguridad");
  if (!container) return;
  container.innerHTML = "<p>cargando logs...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/seguridad/logs");
    var html = "<h3>limpiar logs</h3>";
    html +=
      "<div class='form-group'>" +
      "<label>dias de antiguedad:</label>" +
      "<input id='log_dias' value='30' type='number'>" +
      "<button class='btn btn-outline' onclick='roxy.limpiar_logs()'>limpiar</button>" +
      "</div>";
    html +=
      "<h3>tasa de aciertos historica: " +
      (d.tasa_aciertos != null ? (d.tasa_aciertos * 100).toFixed(1) + "%" : "n/a") +
      "</h3>";
    var columnas = ["id", "tipo", "accion", "email", "ip", "fecha"];
    var filas = (d.logs || []).map(function (l) {
      return [
        l.id,
        l.tipo || "-",
        l.accion || "-",
        l.email || "-",
        l.ip || "-",
        l.fecha || "-",
      ];
    });
    html += roxy.render_tabla(columnas, filas);
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.limpiar_logs = async function () {
  var dias = parseInt(document.getElementById("log_dias").value) || 30;
  roxy.confirmar(
    "eliminar logs con mas de " + dias + " dias de antiguedad?",
    async function () {
      try {
        await roxy.api_call("POST", "/api/admin/seguridad/logs/limpiar", {
          dias: dias,
        });
        roxy.toast("logs limpiados", "toast-success");
        roxy.cargar_seguridad();
      } catch (e) {
        roxy.toast("error: " + e.message, "toast-error");
      }
    }
  );
};