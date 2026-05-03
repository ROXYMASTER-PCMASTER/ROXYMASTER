// admin_proyecciones.js - panel de proyecciones financieras v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_proyecciones = function () {
  // se invoca desde kpi al mismo tiempo, el panel se carga en tab_proyecciones
  var container = document.getElementById("tab_proyecciones");
  if (!container) return;
  roxy._cargar_proyecciones_impl(container);
};

roxy._cargar_proyecciones_impl = async function (container) {
  try {
    var d = await roxy.api_call("GET", "/api/admin/proyecciones");
    var html =
      "<div class='proyecciones-grid'>" +
      d.escenarios
        .map(function (e) {
          return (
            "<div class='proy-card'>" +
            "<span class='proy-titulo'>" +
            e.meses +
            " meses</span>" +
            "<span class='proy-valor'>" +
            e.usuarios_estimados +
            " usuarios</span>" +
            "<span class='proy-sub'>" +
            e.perfiles_estimados +
            " perfiles</span>" +
            "<span class='proy-sub'>tokens emitidos: " +
            e.tokens_emitidos_periodo +
            "</span>" +
            "<span class='proy-sub'>circulantes: " +
            e.tokens_circulantes_est +
            "</span>" +
            "<span class='proy-sub'>margen dueno: " +
            e.margen_dueno +
            "</span>" +
            "<span class='proy-sub'>ganancia granjeros: " +
            e.ganancia_granjeros +
            "</span><span class='proy-sub'>comisiones: " +
            e.comisiones_est +
            "</span>" +
            "</div>"
          );
        })
        .join("") +
      "</div>";
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      '<p style="color:#8b949e">proyecciones no disponibles</p>';
  }
};