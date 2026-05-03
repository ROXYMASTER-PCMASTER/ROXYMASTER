// admin_mensajes.js - panel de mensajes administrativos con alcance v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_mensajes = async function () {
  var container = document.getElementById("tab_mensajes");
  if (!container) return;
  container.innerHTML = "<p>cargando mensajes...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/mensajes/historial");
    var columnas = ["id", "origen", "destino", "texto", "leido", "fecha"];
    var filas = d.mensajes.map(function (m) {
      return [
        m.id,
        m.origen_email,
        m.destino_email,
        m.texto.slice(0, 40) + (m.texto.length > 40 ? "..." : ""),
        m.leido ? "si" : "no",
        m.fecha || "-",
      ];
    });
    container.innerHTML =
      "<h3>enviar mensaje masivo</h3>" +
      "<div style='margin-bottom:16px;'>" +
      "<div class='form-group'>" +
      "<label>texto:</label>" +
      "<input id='mtexto' placeholder='escribe el mensaje...' style='flex:1'>" +
      "</div>" +
      "<div class='form-group'>" +
      "<label>alcance:</label>" +
      "<select id='malcance' onchange='roxy.cambiar_alcance()'>" +
      "<option value='todos'>todos</option>" +
      "<option value='por_rol'>por rol</option>" +
      "<option value='especificos'>especificos</option>" +
      "</select>" +
      "<span id='rol_selector' style='display:none'>" +
      "<select id='mrol'>" +
      "<option>usuario</option><option>admin</option><option>superadmin</option>" +
      "</select>" +
      "</span>" +
      "<span id='ids_selector' style='display:none'>" +
      "<input id='mids' placeholder='ids separados por coma'>" +
      "</span>" +
      "<button class='btn' onclick='roxy.enviar_mensaje()'>enviar</button>" +
      "</div>" +
      "</div>" +
      "<h3>historial</h3>" +
      roxy.render_tabla(columnas, filas);
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy.cambiar_alcance = function () {
  var alc = document.getElementById("malcance").value;
  document.getElementById("rol_selector").style.display =
    alc === "por_rol" ? "inline" : "none";
  document.getElementById("ids_selector").style.display =
    alc === "especificos" ? "inline" : "none";
};

roxy.enviar_mensaje = async function () {
  var texto = document.getElementById("mtexto").value.trim();
  if (!texto) {
    roxy.toast("escribe un mensaje", "toast-error");
    return;
  }
  var alcance = document.getElementById("malcance").value;
  var body = { texto: texto, alcance: alcance };
  if (alcance === "por_rol") {
    body.rol = document.getElementById("mrol").value;
  }
  if (alcance === "especificos") {
    var raw = document.getElementById("mids").value;
    body.user_ids = raw.split(",").map(function (s) {
      return parseInt(s.trim());
    });
  }
  try {
    await roxy.api_call("POST", "/api/admin/mensajes/enviar", body);
    roxy.toast("mensaje enviado", "toast-success");
    document.getElementById("mtexto").value = "";
    roxy.cargar_mensajes();
  } catch (e) {
    roxy.toast("error: " + e.message, "toast-error");
  }
};