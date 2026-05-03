// admin_perfiles.js - panel de perfiles con historial de fallos v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_perfiles = async function () {
  var container = document.getElementById("tab_perfiles");
  if (!container) return;
  container.innerHTML = "<p>cargando perfiles...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/perfiles");
    var columnas = [
      "id",
      "usuario_id",
      "email dueno",
      "nombre",
      "apellido",
      "tipo_iphone",
      "estado",
      "uptime",
    ];
    var filas = d.perfiles.map(function (p) {
      return [
        p.id,
        p.usuario_id,
        p.email_dueno || "-",
        p.nombre || "-",
        p.apellido || "-",
        p.tipo_iphone || "-",
        p.estado || "-",
        p.uptime_horas || 0,
      ];
    });
    var acciones = [
      {
        label: "fallos",
        onclick:
          "roxy.ver_fallos_perfil(this.parentElement.parentElement.cells[0].textContent.trim())",
      },
      {
        label: "editar",
        onclick:
          "roxy.mostrar_editar_perfil(this.parentElement.parentElement.cells[0].textContent.trim())",
      },
    ];
    container.innerHTML = roxy.render_tabla(columnas, filas, acciones);
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.ver_fallos_perfil = async function (pid) {
  try {
    var d = await roxy.api_call(
      "GET",
      "/api/admin/perfiles/historial_fallos/" + pid
    );
    var hist = d.historial || [];
    var html = "<h3>historial de fallos perfil #" + pid + "</h3>";
    if (!hist.length) {
      html += '<p style="color:#8b949e">sin fallos registrados.</p>';
    } else {
      html +=
        "<div class='scrollable'><table><thead><tr><th>inicio</th><th>fin</th><th>resultado</th><th>error</th></tr></thead><tbody>";
      hist.forEach(function (f) {
        html +=
          "<tr><td>" +
          (f.inicio || "-") +
          "</td><td>" +
          (f.fin || "-") +
          "</td><td>" +
          (f.resultado || "-") +
          "</td><td>" +
          (f.error || "-") +
          "</td></tr>";
      });
      html += "</tbody></table></div>";
    }
    html +=
      "<button class='btn btn-outline' onclick='this.parentElement.innerHTML=\"\"'>cerrar</button>";
    var popup = document.createElement("div");
    popup.className = "modal-overlay";
    popup.innerHTML =
      "<div class='modal-box' onclick='event.stopPropagation()'>" +
      html +
      "</div>";
    popup.onclick = function () {
      popup.remove();
    };
    document.getElementById("tab_perfiles").appendChild(popup);
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};

roxy.mostrar_editar_perfil = async function (pid) {
  try {
    var d = await roxy.api_call(
      "GET",
      "/api/admin/perfiles/historial_fallos/" + pid
    );
    var panel = document.getElementById("edit_perfil_panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "edit_perfil_panel";
      document.getElementById("tab_perfiles").appendChild(panel);
    }
    panel.innerHTML =
      "<div class='modal-overlay' onclick='this.parentElement.innerHTML=\"\"'>" +
      "<div class='modal-box' onclick='event.stopPropagation()'>" +
      "<h3>editar perfil #" +
      pid +
      "</h3>" +
      "<div class='form-group'><label>estado:</label><select id='ep_estado'>" +
      ["activo", "pausado", "baneado", "pendiente"]
        .map(function (e) {
          return "<option>" + e + "</option>";
        })
        .join("") +
      "</select></div>" +
      "<button class='btn' onclick='roxy.guardar_editar_perfil(" +
      pid +
      ")'>guardar</button>" +
      "<button class='btn btn-outline' onclick='document.getElementById(\"edit_perfil_panel\").innerHTML=\"\"'>cancelar</button>" +
      "</div></div>";
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};

roxy.guardar_editar_perfil = async function (pid) {
  try {
    await roxy.api_call("PUT", "/api/admin/perfiles/" + pid, {
      estado: document.getElementById("ep_estado").value,
    });
    document.getElementById("edit_perfil_panel").innerHTML = "";
    roxy.toast("perfil actualizado", "toast-success");
    roxy.cargar_perfiles();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};