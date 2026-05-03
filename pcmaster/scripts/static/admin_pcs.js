// admin_pcs.js - panel de pcbots v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_pcs = async function () {
  var container = document.getElementById("tab_pcs");
  if (!container) return;
  container.innerHTML = "<p>cargando pcbots...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/pcs");
    var columnas = ["id", "email", "pcbot_id", "modo", "uptime_horas", "perfiles"];
    var filas = d.pcs.map(function (p) {
      return [
        p.id,
        p.email,
        p.pcbot_id || "-",
        p.modo || "-",
        p.uptime_horas || 0,
        p.perfiles_asociados || 0,
      ];
    });
    var acciones = [
      {
        label: "editar",
        onclick:
          "roxy.editar_pc(this.parentElement.parentElement.cells[0].textContent.trim())",
      },
    ];
    container.innerHTML =
      roxy.render_tabla(columnas, filas, acciones) +
      "<div id='edit_pc_panel'></div>";
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.editar_pc = function (uid) {
  var panel = document.getElementById("edit_pc_panel");
  panel.innerHTML =
    "<div class='modal-overlay' onclick='this.parentElement.innerHTML=\"\"'>" +
    "<div class='modal-box' onclick='event.stopPropagation()'>" +
    "<h3>editar pc #" +
    uid +
    "</h3>" +
    "<div class='form-group'><label>modo:</label><select id='epc_modo'>" +
    ["conectado", "desconectado", "mantenimiento"]
      .map(function (m) {
        return "<option>" + m + "</option>";
      })
      .join("") +
    "</select></div>" +
    "<button class='btn' onclick='roxy.guardar_pc(" +
    uid +
    ")'>guardar</button>" +
    "<button class='btn btn-outline' onclick='document.getElementById(\"edit_pc_panel\").innerHTML=\"\"'>cancelar</button>" +
    "</div></div>";
};

roxy.guardar_pc = async function (uid) {
  try {
    await roxy.api_call("PUT", "/api/admin/pcs/" + uid, {
      modo: document.getElementById("epc_modo").value,
    });
    document.getElementById("edit_pc_panel").innerHTML = "";
    roxy.toast("pc actualizada", "toast-success");
    roxy.cargar_pcs();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};