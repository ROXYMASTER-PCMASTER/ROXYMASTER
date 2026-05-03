// admin_tokenomia.js - panel de variables tokenomicas con auto-save v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_tokenomia = async function () {
  var container = document.getElementById("tab_tokenomia");
  if (!container) return;
  container.innerHTML = "<p>cargando variables...</p>";
  try {
    var d = await roxy.api_call("GET", "/api/admin/variables");
    var vars = d.variables || {};
    var html = "<div class='tokenomia-grid'>";
    var claves = [
      "k",
      "fx",
      "p_token",
      "g_default",
      "h",
      "hh_mult",
      "min_uptime",
      "min_fiabilidad",
      "max_perfiles_pc",
      "comision_marketplace",
    ];
    claves.forEach(function (c) {
      html +=
        "<div class='var-row'>" +
        "<label class='var-label'>" +
        c +
        "</label>" +
        "<input class='var-input' id='var_" +
        c +
        "' value='" +
        (vars[c] || "") +
        "' onchange='roxy.auto_save_var(\"" +
        c +
        "\")' onblur='roxy.auto_save_var(\"" +
        c +
        "\")'>" +
        "</div>";
    });
    html +=
      "<button class='btn btn-outline' onclick='roxy.restablecer_vars()'>restablecer valores predeterminados</button>";
    html += "</div>";
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error: ' + e.message + "</p>";
  }
};

roxy._var_timer = {};
roxy.auto_save_var = function (clave) {
  if (roxy._var_timer[clave]) clearTimeout(roxy._var_timer[clave]);
  roxy._var_timer[clave] = setTimeout(async function () {
    try {
      var valor = document.getElementById("var_" + clave).value;
      await roxy.api_call("PUT", "/api/admin/variables", {
        clave: clave,
        valor: valor,
      });
      roxy.toast(clave + " actualizada", "toast-success");
    } catch (e) {
      roxy.toast("error en " + clave + ": " + e.message, "toast-error");
    }
  }, 800);
};

roxy.restablecer_vars = async function () {
  roxy.confirmar(
    "restablecer todas las variables a valores predeterminados?",
    async function () {
      try {
        await roxy.api_call("POST", "/api/admin/variables/restablecer");
        roxy.toast("variables restablecidas", "toast-success");
        roxy.cargar_tokenomia();
      } catch (e) {
        roxy.toast("error: " + e.message, "toast-error");
      }
    }
  );
};