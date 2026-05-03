// admin_kpi.js - panel kpi con tarjetas interactivas v8.3
// todos los nombres en minusculas, utf-8 sin bom
"use strict";
roxy.cargar_kpi = async function () {
  var container = document.getElementById("tab_kpi");
  if (!container) return;
  try {
    var d = await roxy.api_call("GET", "/api/admin/kpi");
    var k = d;
    var t =
      "<div class='kpi-grid'>" +
      roxy.tarjeta_kpi(
        "usuarios",
        k.usuarios.total,
        k.usuarios.activos + " activos",
        "#58a6ff"
      ) +
      roxy.tarjeta_kpi(
        "kbt circulando",
        Number(k.kbt.circulando).toFixed(2),
        "minado: " + Number(k.kbt.total_minado).toFixed(2),
        "#3fb950"
      ) +
      roxy.tarjeta_kpi(
        "reserva",
        Number(k.kbt.reserva_tokens).toFixed(2) + " kbt",
        "",
        "#d29922"
      ) +
      roxy.tarjeta_kpi(
        "volumen 24h",
        Number(k.operaciones.volumen_24h).toFixed(2) + " kbt",
        "retiros pend: " + k.operaciones.retiros_pendientes,
        "#f78166"
      ) +
      roxy.tarjeta_kpi(
        "pcbots",
        k.pcbots.conectados,
        "conectados",
        "#bc8cff"
      ) +
      roxy.tarjeta_kpi(
        "perfiles",
        k.perfiles.total,
        k.perfiles.activos + " activos",
        "#7ee787"
      ) +
      roxy.tarjeta_kpi(
        "happy hour",
        k.happy_hour.activo ? "activo x" + k.happy_hour.multiplicador : "inactivo",
        "",
        k.happy_hour.activo ? "#ff7b72" : "#8b949e"
      ) +
      "</div>";
    container.innerHTML = t;
  } catch (e) {
    container.innerHTML =
      '<p style="color:#ff7b72">error al cargar kpi: ' + e.message + "</p>";
  }
};

roxy.tarjeta_kpi = function (titulo, valor, subtitulo, color) {
  return (
    "<div class='kpi-card' style='border-left:3px solid " +
    color +
    "'>" +
    "<span class='kpi-titulo'>" +
    titulo +
    "</span>" +
    "<span class='kpi-valor'>" +
    valor +
    "</span>" +
    (subtitulo
      ? "<span class='kpi-subtitulo'>" + subtitulo + "</span>"
      : "") +
    "</div>"
  );
};