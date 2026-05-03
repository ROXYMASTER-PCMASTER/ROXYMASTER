// admin_sesiones.js - panel de sesiones activas v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_sesiones = async function () {
  var container = document.getElementById("tab_sesiones");
  if (!container) return;
  container.innerHTML = "<p>cargando sesiones...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/sesiones");
    var columnas = ["usuario_id", "email", "rol", "pcbot_id", "creacion", "expiracion"];
    var filas = d.sesiones.map(function (s) {
      return [
        s.usuario_id,
        s.email,
        s.rol,
        s.pcbot_id || "-",
        s.fecha_creacion || "-",
        s.fecha_expiracion || "-",
      ];
    });
    var acciones = [
      {
        label: "cerrar",
        onclick:
          "roxy.cerrar_sesion_admin(this.parentElement.parentElement.cells[0].textContent.trim())",
      },
    ];
    container.innerHTML = roxy.render_tabla(columnas, filas, acciones);
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.cerrar_sesion_admin = async function (uid) {
  try {
    var d = await roxy.api_call("GET", "/api/admin/sesiones");
    var sesion = d.sesiones.find(function (s) {
      return s.usuario_id == uid;
    });
    if (!sesion) {
      roxy.toast("sesion no encontrada", "toast-error");
      return;
    }
    await roxy.api_call(
      "DELETE",
      "/api/admin/sesiones/" + sesion.token
    );
    roxy.toast("sesion cerrada", "toast-success");
    roxy.cargar_sesiones();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};