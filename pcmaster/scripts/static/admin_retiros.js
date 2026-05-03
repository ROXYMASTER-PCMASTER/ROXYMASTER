// admin_retiros.js - panel de retiros pendientes v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_retiros = async function () {
  var container = document.getElementById("tab_retiros");
  if (!container) return;
  container.innerHTML = "<p>cargando retiros...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/kbt/retiros?estado=pendiente");
    var columnas = ["id", "usuario_id", "monto", "estado", "direccion", "fecha_solicitud"];
    var filas = d.retiros.map(function (r) {
      return [
        r.id,
        r.usuario_id,
        r.monto_kbt || r.monto,
        r.estado,
        r.direccion || r.destino || "-",
        r.fecha_solicitud || "-",
      ];
    });
    var acciones = [
      {
        label: "aprobar",
        onclick:
          "roxy.procesar_retiro(this.parentElement.parentElement.cells[0].textContent.trim(),'aprobar')",
      },
      {
        label: "rechazar",
        onclick:
          "roxy.procesar_retiro(this.parentElement.parentElement.cells[0].textContent.trim(),'rechazar')",
      },
    ];
    container.innerHTML = roxy.render_tabla(columnas, filas, acciones);
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.procesar_retiro = async function (rid, accion) {
  roxy.confirmar(
    "confirmas " + accion + " el retiro #" + rid + "?",
    async function () {
      try {
        await roxy.api_call("POST", "/api/admin/retiros/procesar", {
          retiro_id: parseInt(rid),
          accion: accion,
        });
        roxy.toast("retiro " + accion + "do", "toast-success");
        roxy.cargar_retiros();
      } catch (e) {
        roxy.toast("error: " + e.message, "toast-error");
      }
    }
  );
};