// admin_usuarios.js - panel de usuarios con edicion inline v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_usuarios = async function () {
  var container = document.getElementById("tab_usuarios");
  if (!container) return;
  container.innerHTML = "<p>cargando usuarios...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/usuarios");
    var columnas = [
      "id",
      "email",
      "username",
      "rol",
      "pcbot_id",
      "modo",
      "activo",
    ];
    var filas = d.usuarios.map(function (u) {
      return [
        u.id,
        u.email,
        u.username || "-",
        u.rol,
        u.pcbot_id || "-",
        u.modo || "-",
        u.activo ? "si" : "no",
      ];
    });
    var acciones = [
      {
        label: "editar",
        onclick:
          "roxy.mostrar_editar_usuario(this.closest('tr').dataset.uid || this.parentElement.parentElement.cells[0].textContent.trim())",
      },
      {
        label: "toggle",
        onclick:
          "roxy.toggle_usuario(this.closest('tr').dataset.uid || this.parentElement.parentElement.cells[0].textContent.trim())",
      },
    ];
    container.innerHTML =
      roxy.render_tabla(columnas, filas, acciones) +
      "<div id='edit_user_panel' class='edit-panel'></div>";
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.mostrar_editar_usuario = async function (uid) {
  try {
    var d = await roxy.api_call("GET", "/api/admin/usuarios/" + uid);
    var u = d.usuario;
    var panel = document.getElementById("edit_user_panel");
    panel.innerHTML =
      "<div class='modal-overlay' onclick='this.parentElement.innerHTML=\"\"'>" +
      "<div class='modal-box' onclick='event.stopPropagation()'>" +
      "<h3>editar usuario #" +
      u.id +
      "</h3>" +
      "<div class='form-group'><label>username:</label><input id='eu_username' value='" +
      (u.username || "") +
      "'></div>" +
      "<div class='form-group'><label>email:</label><input id='eu_email' value='" +
      u.email +
      "'></div>" +
      "<div class='form-group'><label>rol:</label><select id='eu_rol'>" +
      ["usuario", "admin", "superadmin"]
        .map(function (r) {
          return (
            "<option " +
            (r === u.rol ? "selected" : "") +
            ">" +
            r +
            "</option>"
          );
        })
        .join("") +
      "</select></div>" +
      "<div class='form-group'><label>activo:</label><select id='eu_activo'>" +
      "<option value='1' " +
      (u.activo ? "selected" : "") +
      ">si</option>" +
      "<option value='0' " +
      (!u.activo ? "selected" : "") +
      ">no</option>" +
      "</select></div>" +
      "<button class='btn' onclick='roxy.guardar_editar_usuario(" +
      uid +
      ")'>guardar</button>" +
      "<button class='btn btn-outline' onclick='document.getElementById(\"edit_user_panel\").innerHTML=\"\"'>cancelar</button>" +
      "</div></div>";
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};

roxy.guardar_editar_usuario = async function (uid) {
  try {
    var body = {
      username: document.getElementById("eu_username").value,
      email: document.getElementById("eu_email").value,
      rol: document.getElementById("eu_rol").value,
      activo: parseInt(document.getElementById("eu_activo").value),
    };
    await roxy.api_call("PUT", "/api/admin/usuarios/" + uid, body);
    document.getElementById("edit_user_panel").innerHTML = "";
    roxy.toast("usuario actualizado", "toast-success");
    roxy.cargar_usuarios();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};

roxy.toggle_usuario = async function (uid) {
  try {
    var d = await roxy.api_call("GET", "/api/admin/usuarios/" + uid);
    var nuevo = d.usuario.activo ? 0 : 1;
    await roxy.api_call("POST", "/api/admin/usuarios/" + uid + "/toggle", {
      activo: nuevo,
    });
    roxy.toast("usuario " + (nuevo ? "activado" : "desactivado"), "toast-success");
    roxy.cargar_usuarios();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};