"use strict";
/* panel_admin.js - modulo administracion de recursos */
/* version 1.1 - botones listar todos + tabla_editable integrada */
/* todo en minusculas */

(function () {

  // ===== helper para cargar tabla generica =====
  function cargarTabla(tablaId, url, columnas, renderFn) {
    var el = document.getElementById(tablaId);
    if (!el) { return; }
    el.innerHTML = '<div class="loading-placeholder">cargando</div>';
    roxy.api(url)
      .then(function (data) {
        var lista = data.usuarios || data.perfiles || data.pcs || data.sesiones || data.retiros || data.datos || data.eventos || data.proyecciones || data || [];
        if (!Array.isArray(lista)) { lista = []; }
        if (!lista.length) {
          el.innerHTML = '<div class="text-center text-muted p-3">sin datos</div>';
          return;
        }
        var html = '<table class="table table-hover"><thead><tr>';
        columnas.forEach(function (c) { html += '<th>' + roxy.escaparHtml(c) + '</th>'; });
        html += '<th>accion</th></tr></thead><tbody>';
        lista.forEach(function (item, idx) {
          html += '<tr>';
          columnas.forEach(function (c) {
            var val = renderFn ? renderFn(item, c) : item[c];
            if (val === undefined || val === null) { val = "-"; }
            html += '<td>' + roxy.escaparHtml(String(val)) + '</td>';
          });
          html += '<td><button class="btn btn-sm btn-secondary" onclick="roxy.toast(\'detalle no implementado\',\'info\')">ver</button></td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
        el.innerHTML = html;
      })
      .catch(function (err) {
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  }

  // ===== helper para cargar tabla editable =====
  function cargarTablaEditable(tablaId, url, columnas, opciones) {
    var el = document.getElementById(tablaId);
    if (!el) { return; }
    if (typeof window.renderizarTablaEditable !== "function") {
      cargarTabla(tablaId, url, columnas, opciones ? opciones.renderFn : null);
      return;
    }
    el.innerHTML = '<div class="loading-placeholder">cargando</div>';
    roxy.api(url)
      .then(function (data) {
        var lista = data.usuarios || data.perfiles || data.pcs || data.sesiones || data.retiros || data.datos || data.eventos || data.proyecciones || data || [];
        if (!Array.isArray(lista)) { lista = []; }
        window.renderizarTablaEditable(el, lista, columnas, opciones || {});
      })
      .catch(function (err) {
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  }

  // ===== boton listar todos =====
  function agregarBotonListarTodos(tablaId, urlCompleta, columnas) {
    var contenedor = document.getElementById(tablaId);
    if (!contenedor) { return; }
    var btn = document.createElement("button");
    btn.className = "btn btn-sm btn-outline-info mb-2";
    btn.textContent = "listar todos";
    btn.onclick = function () {
      cargarTabla(tablaId, urlCompleta, columnas);
    };
    contenedor.parentNode.insertBefore(btn, contenedor.nextSibling);
  }

  // ===== usuarios =====
  roxy.onTab("usuarios", function () {
    var contenedor = document.getElementById("tab_usuarios");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_usuarios" placeholder="buscar email..." style="width:250px">'
      + '</div>'
      + '<div id="tabla_usuarios"></div>';
    cargarTablaEditable("tabla_usuarios", "/usuarios",
      ["usuario_id", "email", "rol", "saldo", "activo", "creado"],
      { editable: true, endpoint: "/usuarios" }
    );
    agregarBotonListarTodos("tabla_usuarios", "/usuarios?q=&rol=&estado=",
      ["usuario_id", "email", "rol", "saldo", "activo", "creado"]
    );
    document.getElementById("filtro_usuarios").addEventListener("input", function () {
      var q = this.value.toLowerCase();
      document.querySelectorAll("#tabla_usuarios tbody tr").forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // ===== perfiles =====
  roxy.onTab("perfiles", function () {
    var contenedor = document.getElementById("tab_perfiles");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_perfiles" placeholder="buscar..." style="width:250px">'
      + '</div>'
      + '<div id="tabla_perfiles"></div>';
    cargarTablaEditable("tabla_perfiles", "/perfiles",
      ["id", "nombre", "email", "telefono", "creado"],
      { editable: true, endpoint: "/perfiles" }
    );
    agregarBotonListarTodos("tabla_perfiles", "/perfiles?q=&estado=&dueno=",
      ["id", "nombre", "email", "telefono", "creado"]
    );
    document.getElementById("filtro_perfiles").addEventListener("input", function () {
      var q = this.value.toLowerCase();
      document.querySelectorAll("#tabla_perfiles tbody tr").forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // ===== pcs =====
  roxy.onTab("pcs", function () {
    var contenedor = document.getElementById("tab_pcs");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_pcs" placeholder="buscar pc..." style="width:250px">'
      + '</div>'
      + '<div id="tabla_pcs"></div>';
    cargarTablaEditable("tabla_pcs", "/pcs",
      ["id", "nombre", "estado", "ip", "ultimo_ping", "creado"],
      { editable: true, endpoint: "/pcs" }
    );
    agregarBotonListarTodos("tabla_pcs", "/pcs?q=&modo=",
      ["id", "nombre", "estado", "ip", "ultimo_ping", "creado"]
    );
    document.getElementById("filtro_pcs").addEventListener("input", function () {
      var q = this.value.toLowerCase();
      document.querySelectorAll("#tabla_pcs tbody tr").forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // ===== sesiones =====
  roxy.onTab("sesiones", function () {
    var contenedor = document.getElementById("tab_sesiones");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_sesiones" placeholder="buscar..." style="width:250px">'
      + '</div>'
      + '<div id="tabla_sesiones"></div>';
    cargarTabla("tabla_sesiones", "/sesiones", ["sesion_id", "usuario", "ip", "inicio", "expira", "activo"]);
    document.getElementById("filtro_sesiones").addEventListener("input", function () {
      var q = this.value.toLowerCase();
      document.querySelectorAll("#tabla_sesiones tbody tr").forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // ===== retiros =====
  roxy.onTab("retiros", function () {
    var contenedor = document.getElementById("tab_retiros");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_retiros" placeholder="buscar..." style="width:250px">'
      + '</div>'
      + '<div id="tabla_retiros"></div>';
    cargarTabla("tabla_retiros", "/retiros?estado=", ["id", "usuario", "monto", "estado", "solicitado", "procesado"]);
    document.getElementById("filtro_retiros").addEventListener("input", function () {
      var q = this.value.toLowerCase();
      document.querySelectorAll("#tabla_retiros tbody tr").forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // ===== mensajes =====
  roxy.onTab("mensajes", function () {
    var contenedor = document.getElementById("tab_mensajes");
    if (!contenedor) { return; }
    contenedor.innerHTML = ""
      + '<div class="filtros">'
      + '<input class="form-control" id="filtro_mensajes" placeholder="buscar..." style="width:250px">'
      + '</div>'
      + '<div id="lista_mensajes"></div>';
    roxy.api("/mensajes/historial")
      .then(function (data) {
        var el = document.getElementById("lista_mensajes");
        if (!el) { return; }
        var mensajes = data.mensajes || data.resultados || data.datos || data || [];
        if (!Array.isArray(mensajes)) { mensajes = []; }
        if (!mensajes.length) {
          el.innerHTML = '<div class="text-center text-muted p-3">sin mensajes</div>';
          return;
        }
        el.innerHTML = mensajes.map(function (m) {
          return '<div class="mensaje-row">'
            + '<div class="m-de">de: ' + roxy.escaparHtml(m.de || m.remitente || m.usuario || "-") + '</div>'
            + '<div class="m-texto">' + roxy.escaparHtml(m.texto || m.mensaje || m.contenido || "") + '</div>'
            + '<div class="m-fecha">' + roxy.escaparHtml(m.fecha || m.timestamp || m.creado || "") + '</div>'
            + '</div>';
        }).join("");
        document.getElementById("filtro_mensajes").addEventListener("input", function () {
          var q = this.value.toLowerCase();
          document.querySelectorAll(".mensaje-row").forEach(function (el) {
            el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
          });
        });
      })
      .catch(function (err) {
        var el = document.getElementById("lista_mensajes");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  });

  // ===== tokenomia =====
  roxy.onTab("tokenomia", function () {
    var contenedor = document.getElementById("tab_tokenomia");
    if (!contenedor) { return; }
    contenedor.innerHTML = '<div id="tokenomia_contenido"></div>';
    roxy.api("/api/admin/tokenomia/estado")
      .then(function (data) {
        var el = document.getElementById("tokenomia_contenido");
        if (!el) { return; }
        var vars = data.variables || data.parametros || data;
        if (typeof vars === "object" && !Array.isArray(vars)) {
          var html = '<div class="card"><div class="card-header">variables de tokenomia</div><div class="card-body">';
          Object.keys(vars).forEach(function (k) {
            html += '<div class="var-row">'
              + '<span class="var-label">' + roxy.escaparHtml(k) + '</span>'
              + '<span class="var-input">' + roxy.escaparHtml(String(vars[k])) + '</span>'
              + '</div>';
          });
          html += '</div></div>';
          // corregir: mostrar datos reales de tokenomia
          if (data.suministro_total !== undefined) {
            html += '<div class="card mt-2"><div class="card-header">datos de tokenomia</div><div class="card-body">'
              + '<p>suministro total: ' + data.suministro_total + '</p>'
              + '<p>suministro circulante: ' + data.suministro_circulante + '</p>'
              + '<p>precio estimado: $' + (data.precio_estimado || 0) + '</p>'
              + '<p>market cap: $' + (data.market_cap || 0) + '</p>'
              + '</div></div>';
          }
          el.innerHTML = html;
        } else {
          el.innerHTML = '<div class="text-center text-muted p-3">' + JSON.stringify(data) + '</div>';
        }
      })
      .catch(function (err) {
        var el = document.getElementById("tokenomia_contenido");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  });

  // ===== proyecciones =====
  roxy.onTab("proyecciones", function () {
    var contenedor = document.getElementById("tab_proyecciones");
    if (!contenedor) { return; }
    contenedor.innerHTML = '<div id="proyecciones_grid"></div>';
    roxy.api("/api/admin/proyecciones")
      .then(function (data) {
        var el = document.getElementById("proyecciones_grid");
        if (!el) { return; }
        var lista = data.proyecciones || data || [];
        if (!Array.isArray(lista)) { lista = []; }
        if (!lista.length) {
          el.innerHTML = '<div class="text-center text-muted p-3">sin proyecciones</div>';
          return;
        }
        el.className = "proy-grid";
        el.innerHTML = lista.map(function (p) {
          return '<div class="proy-card">'
            + '<div class="proy-titulo">' + roxy.escaparHtml(p.titulo || p.nombre || "proyeccion") + '</div>'
            + (p.descripcion ? '<div class="proy-linea">' + roxy.escaparHtml(p.descripcion) + '</div>' : "")
            + (p.valor ? '<div class="proy-linea">valor: ' + roxy.escaparHtml(String(p.valor)) + '</div>' : "")
            + (p.fecha ? '<div class="proy-linea">' + roxy.escaparHtml(p.fecha) + '</div>' : "")
            + '</div>';
        }).join("");
      })
      .catch(function (err) {
        var el = document.getElementById("proyecciones_grid");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  });

  // ===== happy_hour =====
  roxy.onTab("happy_hour", function () {
    var contenedor = document.getElementById("tab_happy_hour");
    if (!contenedor) { return; }
    contenedor.innerHTML = '<div id="happy_contenido"></div>';
    roxy.api("/api/admin/happy-hour/estado")
      .then(function (data) {
        var el = document.getElementById("happy_contenido");
        if (!el) { return; }
        if (data.activo || data.happy_hour_activo) {
          el.innerHTML = '<div class="card border-success"><div class="card-header text-success">happy hour activo</div><div class="card-body">'
            + '<p>multiplicador: ' + (data.multiplicador || data.multiplier || "x2") + '</p>'
            + '<p>horario: ' + roxy.escaparHtml(data.horario || data.horario_activo || "activo") + '</p>'
            + '</div></div>';
        } else {
          el.innerHTML = '<div class="card"><div class="card-header">happy hour</div><div class="card-body">'
            + '<p class="text-muted">no hay happy hour activo</p>'
            + '</div></div>';
        }
      })
      .catch(function (err) {
        var el = document.getElementById("happy_contenido");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  });

  // ===== seguridad =====
  roxy.onTab("seguridad", function () {
    var contenedor = document.getElementById("tab_seguridad");
    if (!contenedor) { return; }
    contenedor.innerHTML = '<div id="seguridad_eventos"></div>';
    roxy.api("/seguridad/eventos")
      .then(function (data) {
        var el = document.getElementById("seguridad_eventos");
        if (!el) { return; }
        var eventos = data.eventos || data || [];
        if (!Array.isArray(eventos)) { eventos = []; }
        if (!eventos.length) {
          el.innerHTML = '<div class="text-center text-muted p-3">sin eventos de seguridad</div>';
          return;
        }
        el.innerHTML = eventos.map(function (e) {
          var tipo = (e.tipo || e.level || "info").toLowerCase();
          var clase = "ev-info";
          if (tipo === "critico" || tipo === "critical") { clase = "ev-critico"; }
          else if (tipo === "alerta" || tipo === "warning") { clase = "ev-alerta"; }
          return '<div class="evento-row">'
            + '<span class="ev-tipo ' + clase + '">' + roxy.escaparHtml(tipo) + '</span>'
            + roxy.escaparHtml(e.mensaje || e.descripcion || e.message || "")
            + '<span class="float-end text-muted small">' + roxy.escaparHtml(e.fecha || e.timestamp || e.creado || "") + '</span>'
            + '</div>';
        }).join("");
      })
      .catch(function (err) {
        var el = document.getElementById("seguridad_eventos");
        if (el) { el.innerHTML = '<div class="loading-placeholder">error: ' + roxy.escaparHtml(err.message) + '</div>'; }
      });
  });

})();