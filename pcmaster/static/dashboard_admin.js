// dashboard_admin.js - logica del panel admin roxymaster v8.3
// todos en minusculas, utf-8 sin bom
(function() {
    'use strict';

    var apiBase = '';
    var token = '';
    var rolUsuario = '';
    var emailUsuario = '';
    var kpiAdminCache = null;
    var mensajesCache = [];

    // helpers
    function obtenerToken() {
        var params = new URLSearchParams(window.location.search);
        token = params.get('token') || localStorage.getItem('token') || '';
        return token;
    }

    function api(method, path, body) {
        var opts = { method: method, headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token } };
        if (body) opts.body = JSON.stringify(body);
        return fetch(apiBase + path, opts).then(function(r) {
            if (!r.ok) { return r.text().then(function(t) { try { var j = JSON.parse(t); throw new Error(j.detail || j.error || t); } catch(e) { throw new Error(t); } }); }
            return r.json();
        });
    }

    // notificacion toast
    function mostrarToast(msg, tipo) {
        var el = document.getElementById('toast');
        if (!el) return;
        el.textContent = msg;
        el.className = 'toast show' + (tipo ? ' ' + tipo : '');
        clearTimeout(el._timeout);
        el._timeout = setTimeout(function() { el.className = 'toast'; }, 4000);
    }

    // navegacion de pestañas
    function switchTab(tabId) {
        var tabs = document.querySelectorAll('.tab-content');
        tabs.forEach(function(t) { t.classList.remove('active'); });
        var target = document.getElementById('tab-content-' + tabId);
        if (target) target.classList.add('active');

        var navs = document.querySelectorAll('.admin-sidebar nav button');
        navs.forEach(function(n) { n.classList.remove('active'); });
        var navBtn = document.getElementById('nav-' + tabId);
        if (navBtn) navBtn.classList.add('active');

        var titulos = { 'kpi': 'panel kpi', 'usuarios': 'gestion de usuarios', 'sesiones': 'sesiones activas', 'perfiles': 'perfiles de usuario', 'pcs': 'pcs registradas', 'retiros': 'solicitudes de retiro', 'mensajes': 'mensajes', 'monitoreo': 'monitoreo en vivo', 'tokenomia': 'tokenomia kbt', 'endpoints': 'explorador de endpoints', 'proyecciones': 'proyecciones', 'seguridad': 'seguridad' };
        var tituloEl = document.getElementById('tab-titulo');
        if (tituloEl) tituloEl.textContent = titulos[tabId] || tabId;

        // refrescar badge global en cada pestana
        actualizarBadgeAdmin();

        // cargar datos segun pestana
        switch (tabId) {
            case 'kpi': cargarKPI(); break;
            case 'usuarios': listarUsuarios(); break;
            case 'sesiones': listarSesiones(); break;
            case 'perfiles': listarPerfiles(); break;
            case 'pcs': listarPcs(); break;
            case 'retiros': listarRetiros(); break;
            case 'mensajes': listarMensajesAdmin(); break;
            case 'monitoreo': cargarMonitoreo(); break;
            case 'tokenomia': cargarTokenomia(); break;
            case 'endpoints': cargarIndiceEndpointsAdmin(); break;
        }
    }

    // --- pestana kpi ---
    function cargarKPI() {
        api('GET', '/api/superadmin/kpi').then(function(d) {
            kpiAdminCache = d || {};
            document.getElementById('kpi-usuarios').textContent = (d.usuarios && d.usuarios.total) || '--';
            document.getElementById('kpi-pcbots').textContent = (d.pcbots && d.pcbots.conectados) || '--';
            document.getElementById('kpi-tokens').textContent = ((d.kbt && d.kbt.circulando) || 0).toFixed(1);
            document.getElementById('kpi-pedidos').textContent = (d.operaciones && d.operaciones.comandos_pendientes) || '--';
            document.getElementById('kpi-perfiles').textContent = (d.perfiles && d.perfiles.activos) || '--';
            document.getElementById('kpi-ingresos').textContent = ((d.operaciones && d.operaciones.volumen_24h) || 0).toFixed(2);
        }).catch(function(e) { mostrarToast('error al cargar kpi: ' + e.message, 'error'); });
    }

    function seleccionarKPI(tipo, el) {
        var cards = document.querySelectorAll('.kpi-card');
        cards.forEach(function(c) { c.classList.remove('kpi-selected'); });
        if (el) el.classList.add('kpi-selected');

        var detalle = document.getElementById('kpi-detalle');
        if (!detalle) return;
        detalle.innerHTML = '<div class="kpi-detalle-loading">cargando detalle...</div>';
        detalle.classList.add('show');

        if (!kpiAdminCache) {
            detalle.innerHTML = '<div class="kpi-detalle-error">sin datos de kpi</div>';
            return;
        }
        var dataset = [];
        if (tipo === 'usuarios' && kpiAdminCache.usuarios) {
            dataset = [{ nombre: 'total', valor: kpiAdminCache.usuarios.total }, { nombre: 'activos', valor: kpiAdminCache.usuarios.activos }, { nombre: 'admin', valor: kpiAdminCache.usuarios.admin }];
        } else if (tipo === 'pcbots' && kpiAdminCache.pcbots) {
            dataset = [{ nombre: 'registrados', valor: kpiAdminCache.pcbots.total_registrados }, { nombre: 'conectados', valor: kpiAdminCache.pcbots.conectados }];
        } else if (tipo === 'tokens' && kpiAdminCache.kbt) {
            dataset = [{ nombre: 'circulando', valor: kpiAdminCache.kbt.circulando }, { nombre: 'minado', valor: kpiAdminCache.kbt.total_minado }, { nombre: 'recolectado', valor: kpiAdminCache.kbt.total_recolectado }];
        } else if (tipo === 'pedidos' && kpiAdminCache.operaciones) {
            dataset = [{ nombre: 'comandos_pendientes', valor: kpiAdminCache.operaciones.comandos_pendientes }, { nombre: 'retiros_pendientes', valor: kpiAdminCache.operaciones.retiros_pendientes }, { nombre: 'sesiones_activas', valor: kpiAdminCache.operaciones.sesiones_activas }];
        } else if (tipo === 'perfiles' && kpiAdminCache.perfiles) {
            dataset = [{ nombre: 'total', valor: kpiAdminCache.perfiles.total }, { nombre: 'activos', valor: kpiAdminCache.perfiles.activos }];
        } else if (tipo === 'ingresos' && kpiAdminCache.operaciones) {
            dataset = [{ nombre: 'volumen_24h', valor: kpiAdminCache.operaciones.volumen_24h }];
        }
        if (dataset.length === 0) {
            detalle.innerHTML = '<div class="kpi-detalle-error">sin datos disponibles</div>';
            return;
        }
        var html = '<div class="kpi-detalle-header">' + tipo + '</div>';
            html += '<div class="kpi-detalle-grid">';
            dataset.forEach(function(item) {
                var val = item.valor || item.total || item.cantidad || '--';
                html += '<div class="kpi-detalle-item" onclick="window.detalleItem(\'' + (tipo + '_' + (item.id || item.nombre || '')) + '\')">';
                html += '<div class="item-label">' + (item.nombre || item.label || '') + '</div>';
                html += '<div class="item-val">' + val + '</div>';
                html += '</div>';
            });
            html += '</div>';
            html += '<div id="n3-panel" class="n3-panel"></div>';
            detalle.innerHTML = html;
    }

    // --- pestana usuarios ---
    var usuariosCache = [];

    function listarUsuarios() {
        api('GET', '/api/admin/usuarios').then(function(lista) {
            usuariosCache = Array.isArray(lista) ? lista : (lista.usuarios || []);
            renderizarUsuarios();
        }).catch(function(e) { mostrarToast('error al listar usuarios: ' + e.message, 'error'); });
    }

    function renderizarUsuarios() {
        var filtroEmail = (document.getElementById('filtro-usuarios') || {}).value || '';
        var filtroRol = (document.getElementById('filtro-rol-usuarios') || {}).value || '';
        var filtroEstado = (document.getElementById('filtro-estado-usuarios') || {}).value || '';
        var tbody = document.getElementById('tbody-usuarios');
        if (!tbody) return;
        var filtrados = usuariosCache.filter(function(u) {
            if (filtroEmail && !(u.email || '').toLowerCase().includes(filtroEmail.toLowerCase())) return false;
            if (filtroRol && u.rol !== filtroRol) return false;
            if (filtroEstado === 'activo' && u.activo !== 1 && u.activo !== true) return false;
            if (filtroEstado === 'inactivo' && (u.activo === 1 || u.activo === true)) return false;
            return true;
        });
        if (filtrados.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">sin usuarios</td></tr>';
            return;
        }
        var html = '';
        filtrados.forEach(function(u) {
            var badgeRol = 'badge-' + (u.rol || 'user');
            var badgeEst = u.activo ? 'badge-activo' : 'badge-inactivo';
            html += '<tr class="fila-usuario" onclick="window.toggleDetalleUsuario(' + (u.id || 0) + ')">';
            html += '<td>' + (u.id || '--') + '</td>';
            html += '<td>' + (u.email || '--') + '</td>';
            html += '<td><span class="badge ' + badgeRol + '">' + (u.rol || 'usuario') + '</span></td>';
            html += '<td><span class="badge ' + badgeEst + '">' + (u.activo ? 'activo' : 'inactivo') + '</span></td>';
            html += '<td>' + (u.pcbot_id || '--') + '</td>';
            html += '<td>' + (u.confianza || u.nivel_confianza || '--') + '</td>';
            html += '<td><button class="btn-accion" onclick="event.stopPropagation();window.editarUsuario(' + (u.id || 0) + ')">editar</button></td>';
            html += '</tr>';
            html += '<tr class="detalle-usuario" id="detalle-' + (u.id || 0) + '" style="display:none;"><td colspan="7"><div class="usuario-detalle-grid"></div></td></tr>';
        });
        tbody.innerHTML = html;
    }

    function filtrarUsuarios() { renderizarUsuarios(); }

    function toggleDetalleUsuario(id) {
        var row = document.getElementById('detalle-' + id);
        if (!row) return;
        if (row.style.display !== 'table-row') {
            row.style.display = 'table-row';
            var grid = row.querySelector('.usuario-detalle-grid');
            if (grid && !grid.hasChildNodes()) {
                var u = usuariosCache.find(function(x) { return x.id === id; });
                if (u) {
                    var campos = [['id', u.id], ['email', u.email], ['rol', u.rol], ['activo', u.activo ? 'si' : 'no'], ['pcbot_id', u.pcbot_id || '--'], ['confianza', u.confianza || u.nivel_confianza || '--'], ['kbt', (u.kbt || u.saldo_kbt || 0) + ' kbt'], ['creado', u.created_at || u.fecha_creacion || '--'], ['ultimo_acceso', u.ultimo_acceso || '--']];
                    var gh = '';
                    campos.forEach(function(c) { gh += '<div class="detalle-campo"><div class="campo-label">' + c[0] + '</div><div class="campo-val">' + (c[1] || '--') + '</div></div>'; });
                    grid.innerHTML = gh;
                }
            }
        } else {
            row.style.display = 'none';
        }
    }

    function editarUsuario(id) {
        var u = usuariosCache.find(function(x) { return x.id === id; });
        if (!u) { mostrarToast('usuario no encontrado', 'error'); return; }
        document.getElementById('modal-titulo').textContent = 'editar usuario #' + id;
        document.getElementById('modal-cuerpo').innerHTML = '<label>email</label><input type="email" id="modal-edit-email" value="' + (u.email || '') + '"><label>rol</label><select id="modal-edit-rol"><option value="usuario">usuario</option><option value="admin">admin</option><option value="granjero">granjero</option><option value="moderador">moderador</option><option value="dueno">dueno</option></select><label>activo</label><select id="modal-edit-activo"><option value="1">si</option><option value="0">no</option></select>';
        document.getElementById('modal-edit-rol').value = u.rol || 'usuario';
        document.getElementById('modal-edit-activo').value = u.activo ? '1' : '0';
        document.getElementById('modal-accion').classList.add('show');
        document.getElementById('modal-btn-confirmar').onclick = function() {
            mostrarToast('edicion directa no disponible en este build', 'error');
        };
    }

    function mostrarModalCrearUsuario() {
        document.getElementById('modal-titulo').textContent = 'crear nuevo usuario';
        document.getElementById('modal-cuerpo').innerHTML = '<label>email</label><input type="email" id="modal-nuevo-email"><label>contrasena</label><input type="password" id="modal-nuevo-pass"><label>rol</label><select id="modal-nuevo-rol"><option value="usuario">usuario</option><option value="admin">admin</option><option value="granjero">granjero</option><option value="moderador">moderador</option><option value="dueno">dueno</option></select>';
        document.getElementById('modal-accion').classList.add('show');
        document.getElementById('modal-btn-confirmar').onclick = function() {
            mostrarToast('creacion directa no disponible en este build', 'error');
        };
    }

    // --- pestana sesiones ---
    function listarSesiones() {
        api('GET', '/api/superadmin/sesiones').then(function(lista) {
            var arr = Array.isArray(lista) ? lista : (lista.sesiones || []);
            var tbody = document.getElementById('tbody-sesiones');
            if (!tbody) return;
            if (arr.length === 0) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">sin sesiones activas</td></tr>'; return; }
            var html = '';
            arr.forEach(function(s) {
                html += '<tr><td>' + (s.token || '--') + '</td><td>' + (s.email || s.usuario || '--') + '</td><td>' + (s.rol || '--') + '</td><td>' + (s.fecha_expiracion || '--') + '</td>';
                html += '<td><button class="btn-accion danger" onclick="revocarSesion(\'' + (s.token_full || '') + '\')">revocar</button></td></tr>';
            });
            tbody.innerHTML = html;
        }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    function revocarSesion(tok) {
        if (!confirm('revocar sesion?')) return;
        api('DELETE', '/api/superadmin/sesiones/' + encodeURIComponent(tok)).then(function() { mostrarToast('sesion revocada', 'success'); listarSesiones(); }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    // --- pestana perfiles ---
    var perfilesCache = [];

    function listarPerfiles() {
        api('GET', '/api/superadmin/perfiles').then(function(lista) {
            perfilesCache = Array.isArray(lista) ? lista : (lista.perfiles || []);
            renderizarPerfiles();
        }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    function renderizarPerfiles() {
        var filtroEstado = (document.getElementById('filtro-estado-perfiles') || {}).value || '';
        var filtroTexto = (document.getElementById('filtro-perfiles') || {}).value || '';
        var tbody = document.getElementById('tbody-perfiles');
        if (!tbody) return;
        var filtrados = perfilesCache.filter(function(p) {
            if (filtroEstado && (p.estado || '').toLowerCase() !== filtroEstado.toLowerCase()) return false;
            if (filtroTexto && !(p.email || p.nombre_perfil || '').toLowerCase().includes(filtroTexto.toLowerCase())) return false;
            return true;
        });
        if (filtrados.length === 0) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">sin perfiles</td></tr>'; return; }
        var html = '';
        filtrados.forEach(function(p) {
            var bEst = 'badge-' + (p.estado === 'activo' ? 'activo' : (p.estado === 'inactivo' ? 'inactivo' : 'pendiente'));
            html += '<tr><td>' + (p.usuario_id || p.user_id || '--') + '</td><td>' + (p.email || '--') + '</td><td><span class="badge ' + bEst + '">' + (p.estado || '--') + '</span></td><td>' + (p.nombre_perfil || '--') + '</td><td><button class="btn-accion" onclick="window.verPerfil(' + (p.id || 0) + ')">ver</button></td></tr>';
        });
        tbody.innerHTML = html;
    }

    function filtrarPerfiles() { renderizarPerfiles(); }

    function verPerfil(id) {
        var p = perfilesCache.find(function(x) { return x.id === id; });
        if (!p) { mostrarToast('perfil no encontrado', 'error'); return; }
        mostrarToast('perfil ' + id + ': ' + JSON.stringify(p), '');
    }

    // --- pestana pcs ---
    var pcsCache = [];

    function listarPcs() {
        api('GET', '/api/superadmin/pcs').then(function(lista) {
            pcsCache = Array.isArray(lista) ? lista : (lista.pcs || []);
            renderizarPcs();
        }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    function renderizarPcs() {
        var filtroModo = (document.getElementById('filtro-modo-pcs') || {}).value || '';
        var tbody = document.getElementById('tbody-pcs');
        if (!tbody) return;
        var filtrados = pcsCache.filter(function(p) {
            if (filtroModo && (p.modo || '').toLowerCase() !== filtroModo.toLowerCase()) return false;
            return true;
        });
        if (filtrados.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">sin pcs registradas</td></tr>'; return; }
        var html = '';
        filtrados.forEach(function(p) {
            html += '<tr><td>' + (p.pcbot_id || p.id || '--') + '</td><td>' + (p.email || '--') + '</td><td>' + (p.modo || '--') + '</td><td>' + ((p.uptime_horas || 0) + ' h') + '</td><td>' + (p.perfiles_asociados || '--') + '</td><td><button class="btn-accion" onclick="window.editarPc(\'' + (p.pcbot_id || p.id || '') + '\')">config</button></td></tr>';
        });
        tbody.innerHTML = html;
    }

    function filtrarPcs() { renderizarPcs(); }

    function editarPc(id) {
        mostrarToast('configurar pc: ' + id, '');
    }

    // --- pestana retiros ---
    function listarRetiros() {
        var estado = (document.getElementById('filtro-estado-retiros') || {}).value || '';
        api('GET', '/api/admin/retiros?estado=' + encodeURIComponent(estado)).then(function(lista) {
            var arr = Array.isArray(lista) ? lista : (lista.retiros || []);
            var tbody = document.getElementById('tbody-retiros');
            if (!tbody) return;
            if (arr.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">sin retiros</td></tr>'; return; }
            var html = '';
            arr.forEach(function(r) {
                var bEst = 'badge-' + (r.estado === 'aprobado' ? 'activo' : (r.estado === 'rechazado' ? 'inactivo' : 'pendiente'));
                html += '<tr><td>' + (r.id || '--') + '</td><td>' + (r.email || r.usuario || '--') + '</td><td>' + (r.cantidad_kbt || r.monto || '--') + ' kbt</td><td><span class="badge ' + bEst + '">' + (r.estado || '--') + '</span></td><td>' + (r.fecha_solicitud || r.fecha || r.created_at || '--') + '</td>';
                html += '<td><button class="btn-accion success" onclick="window.aprobarRetiro(' + (r.id || 0) + ')">aprobar</button> <button class="btn-accion danger" onclick="window.rechazarRetiro(' + (r.id || 0) + ')">rechazar</button></td></tr>';
            });
            tbody.innerHTML = html;
        }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    function aprobarRetiro(id) { api('POST', '/api/superadmin/retiros/procesar', { retiro_id: id, accion: 'aprobar' }).then(function() { mostrarToast('retiro aprobado', 'success'); listarRetiros(); }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); }); }
    function rechazarRetiro(id) { api('POST', '/api/superadmin/retiros/procesar', { retiro_id: id, accion: 'rechazar' }).then(function() { mostrarToast('retiro rechazado', 'success'); listarRetiros(); }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); }); }

    // --- pestana mensajes ---
    function listarMensajesAdmin() {
        api('GET', '/api/superadmin/mensajes/historial').then(function(lista) {
            var arr = Array.isArray(lista) ? lista : (lista.mensajes || []);
            mensajesCache = arr;
            var tbody = document.getElementById('tbody-mensajes');
            if (!tbody) return;
            if (arr.length === 0) { tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">sin mensajes</td></tr>'; return; }
            var html = '';
            arr.forEach(function(m) {
                html += '<tr><td>' + (m.id || '--') + '</td><td>' + (m.origen_email || '--') + '</td><td>' + (m.destino_email || '--') + '</td><td>mensaje</td><td>' + (m.leido ? 'si' : 'no') + '</td><td>' + (m.fecha || m.created_at || '--') + '</td><td><button class="btn-accion" onclick="window.verMensaje(' + (m.id || 0) + ')">ver</button></td></tr>';
            });
            tbody.innerHTML = html;
        }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
    }

    function verMensaje(id) {
        var m = mensajesCache.find(function(x) { return x.id === id; });
        if (!m) { mostrarToast('mensaje no encontrado', 'error'); return; }
        document.getElementById('modal-titulo').textContent = 'mensaje #' + id;
        document.getElementById('modal-cuerpo').innerHTML = '<div class="modal-mensaje">de: ' + (m.origen_email || '--') + '<br>para: ' + (m.destino_email || '--') + '<br>fecha: ' + (m.fecha || '--') + '<br><br>' + (m.texto || 'sin contenido') + '</div>';
        document.getElementById('modal-accion').classList.add('show');
        document.getElementById('modal-btn-confirmar').onclick = cerrarModal;
        document.getElementById('modal-btn-confirmar').textContent = 'cerrar';
    }

    function mostrarModalEnviarMensaje() {
        document.getElementById('modal-titulo').textContent = 'enviar mensaje';
        document.getElementById('modal-cuerpo').innerHTML = '<label>destinatario (email)</label><input type="email" id="modal-msg-para"><label>asunto</label><input type="text" id="modal-msg-asunto"><label>contenido</label><textarea id="modal-msg-cuerpo" rows="4"></textarea>';
        document.getElementById('modal-accion').classList.add('show');
        document.getElementById('modal-btn-confirmar').onclick = function() {
            var data = { email_destino: document.getElementById('modal-msg-para').value, texto: document.getElementById('modal-msg-cuerpo').value };
            api('POST', '/api/superadmin/mensajes/enviar', data).then(function() { mostrarToast('mensaje enviado', 'success'); cerrarModal(); listarMensajesAdmin(); }).catch(function(e) { mostrarToast('error: ' + e.message, 'error'); });
        };
        document.getElementById('modal-btn-confirmar').textContent = 'enviar';
    }

    // --- pestana monitoreo ---
    function cargarMonitoreo() {
        api('GET', '/api/superadmin/kpi').then(function(d) {
            kpiAdminCache = d || {};
            document.getElementById('mon-pcbots').textContent = (d.pcbots && d.pcbots.conectados) || '--';
            document.getElementById('mon-perfiles').textContent = (d.perfiles && d.perfiles.activos) || '--';
            document.getElementById('mon-pedidos').textContent = (d.operaciones && d.operaciones.retiros_pendientes) || '--';
            document.getElementById('mon-comandos').textContent = (d.operaciones && d.operaciones.comandos_pendientes) || '--';
        }).catch(function(e) { mostrarToast('error al cargar monitoreo: ' + e.message, 'error'); });
    }

    function seleccionarMonitoreo(tipo, el) {
        var cards = document.querySelectorAll('#tab-content-monitoreo .kpi-card');
        cards.forEach(function(c) { c.classList.remove('kpi-selected'); });
        if (el) el.classList.add('kpi-selected');
        var detalle = document.getElementById('mon-detalle');
        if (!detalle) return;
        detalle.innerHTML = '<div class="kpi-detalle-loading">cargando...</div>';
        if (!kpiAdminCache) { detalle.innerHTML = '<div class="kpi-detalle-error">sin datos</div>'; return; }
        var items = [];
        if (tipo === 'pcbots') items = [{ nombre: 'registrados', estado: '-', valor: kpiAdminCache.pcbots.total_registrados }, { nombre: 'conectados', estado: '-', valor: kpiAdminCache.pcbots.conectados }];
        if (tipo === 'perfiles') items = [{ nombre: 'total', estado: '-', valor: kpiAdminCache.perfiles.total }, { nombre: 'activos', estado: '-', valor: kpiAdminCache.perfiles.activos }];
        if (tipo === 'pedidos') items = [{ nombre: 'retiros_pendientes', estado: '-', valor: kpiAdminCache.operaciones.retiros_pendientes }];
        if (tipo === 'comandos') items = [{ nombre: 'comandos_pendientes', estado: '-', valor: kpiAdminCache.operaciones.comandos_pendientes }];
        if (items.length === 0) { detalle.innerHTML = '<div class="kpi-detalle-error">sin datos</div>'; return; }
        var html = '<div class="kpi-detalle-header">' + tipo + '</div>';
            html += '<table class="kpi-detalle-table"><thead><tr><th>nombre</th><th>estado</th><th>valor</th></tr></thead><tbody>';
            items.forEach(function(item) { html += '<tr><td>' + (item.nombre || '') + '</td><td>' + (item.estado || '') + '</td><td>' + (item.valor || '') + '</td></tr>'; });
            html += '</tbody></table>';
            detalle.innerHTML = html;
    }

    // --- pestana tokenomia ---
    function cargarTokenomia() {
        api('GET', '/api/superadmin/kpi').then(function(d) {
            kpiAdminCache = d || {};
            document.getElementById('tok-oferta').textContent = ((d.kbt && d.kbt.circulando) || 0).toFixed(1);
            document.getElementById('tok-quemados').textContent = ((d.kbt && d.kbt.total_minado) || 0).toFixed(1);
            document.getElementById('tok-precio').textContent = ((d.kbt && d.kbt.reserva_soles) || 0).toFixed(4);
        }).catch(function(e) { mostrarToast('error al cargar tokenomia: ' + e.message, 'error'); });
    }

    function seleccionarTokenomia(tipo, el) {
        var cards = document.querySelectorAll('#tab-content-tokenomia .kpi-card');
        cards.forEach(function(c) { c.classList.remove('kpi-selected'); });
        if (el) el.classList.add('kpi-selected');
        var detalle = document.getElementById('tok-detalle');
        if (!detalle) return;
        detalle.innerHTML = '<div class="kpi-detalle-loading">cargando...</div>';
        if (!kpiAdminCache || !kpiAdminCache.kbt) { detalle.innerHTML = '<div class="kpi-detalle-error">sin datos</div>'; return; }
        var items = [];
        if (tipo === 'oferta') items = [{ nombre: 'kbt_circulando', valor: kpiAdminCache.kbt.circulando }];
        if (tipo === 'quemados') items = [{ nombre: 'total_minado', valor: kpiAdminCache.kbt.total_minado }, { nombre: 'total_recolectado', valor: kpiAdminCache.kbt.total_recolectado }];
        if (tipo === 'precio') items = [{ nombre: 'reserva_tokens', valor: kpiAdminCache.kbt.reserva_tokens }, { nombre: 'reserva_soles', valor: kpiAdminCache.kbt.reserva_soles }];
        if (items.length === 0) { detalle.innerHTML = '<div class="kpi-detalle-error">sin datos</div>'; return; }
        var html = '<div class="kpi-detalle-header">' + tipo + '</div>';
            html += '<table class="kpi-detalle-table"><thead><tr><th>concepto</th><th>valor</th></tr></thead><tbody>';
            items.forEach(function(item) { html += '<tr><td>' + (item.nombre || item.concepto || '') + '</td><td>' + (item.valor || '') + '</td></tr>'; });
            html += '</tbody></table>';
            detalle.innerHTML = html;
    }

    // --- modal generico ---
    function cerrarModal() {
        document.getElementById('modal-accion').classList.remove('show');
        document.getElementById('modal-btn-confirmar').textContent = 'confirmar';
    }

    // --- cerrar sesion ---
    function cerrarSesion() {
        localStorage.removeItem('token');
        localStorage.removeItem('usuario_email');
        localStorage.removeItem('usuario_rol');
        window.location.href = '/login';
    }

    // --- badge de saldo visible en todas las pestanas ---
    function actualizarBadgeAdmin() {
        api('GET', '/api/superadmin/kpi').then(function(d) {
            var oferta = (d.kbt && d.kbt.circulando) || 0;
            var precio = oferta > 0 ? (((d.kbt && d.kbt.reserva_soles) || 0) / oferta) : 0;
            var badgeKbt = document.getElementById('badge-admin-kbt');
            var badgePen = document.getElementById('badge-admin-pen');
            if (badgeKbt) badgeKbt.textContent = Number(oferta).toFixed(2);
            if (badgePen) badgePen.textContent = (oferta * precio).toFixed(2);
        }).catch(function() {
            // silencioso - el badge se queda con valores por defecto
        });
    }

    // --- init ---
    function init() {
        token = obtenerToken();
        if (!token) { window.location.href = '/login'; return; }
        emailUsuario = localStorage.getItem('usuario_email') || 'admin';
        rolUsuario = localStorage.getItem('usuario_rol') || 'admin';
        var emailEl = document.getElementById('usuario_email');
        if (emailEl) emailEl.textContent = emailUsuario + ' (' + rolUsuario + ')';
        // mostrar elementos segun rol
        if (rolUsuario === 'dueno' || rolUsuario === 'superadmin') {
            var els = document.querySelectorAll('.rol-dueno-only, .rol-admin-only');
            els.forEach(function(el) { el.style.display = ''; });
        } else if (rolUsuario === 'admin') {
            var els2 = document.querySelectorAll('.rol-admin-only');
            els2.forEach(function(el) { el.style.display = ''; });
        }
        // badge global inicial
        actualizarBadgeAdmin();
        // cargar pestana inicial con switchTab para activar visualmente
        switchTab('kpi');
    }

    // exponer funciones globales
    window.switchTab = switchTab;
    window.cargarKPI = cargarKPI;
    window.seleccionarKPI = seleccionarKPI;
    window.listarUsuarios = listarUsuarios;
    window.filtrarUsuarios = filtrarUsuarios;
    window.toggleDetalleUsuario = toggleDetalleUsuario;
    window.editarUsuario = editarUsuario;
    window.mostrarModalCrearUsuario = mostrarModalCrearUsuario;
    window.listarSesiones = listarSesiones;
    window.revocarSesion = revocarSesion;
    window.listarPerfiles = listarPerfiles;
    window.filtrarPerfiles = filtrarPerfiles;
    window.verPerfil = verPerfil;
    window.listarPcs = listarPcs;
    window.filtrarPcs = filtrarPcs;
    window.editarPc = editarPc;
    window.listarRetiros = listarRetiros;
    window.aprobarRetiro = aprobarRetiro;
    window.rechazarRetiro = rechazarRetiro;
    window.listarMensajesAdmin = listarMensajesAdmin;
    window.verMensaje = verMensaje;
    window.mostrarModalEnviarMensaje = mostrarModalEnviarMensaje;
    window.cargarMonitoreo = cargarMonitoreo;
    window.seleccionarMonitoreo = seleccionarMonitoreo;
    window.cargarTokenomia = cargarTokenomia;
    window.seleccionarTokenomia = seleccionarTokenomia;
    window.cerrarModal = cerrarModal;
    window.cerrarSesion = cerrarSesion;
    window.cargarIndiceEndpointsAdmin = function() {
        api('GET', '/api/endpoints').then(function(d) {
            var tbody = document.getElementById('tbody-endpoints-admin');
            if (!tbody) return;
            var html = '';
            (d.categorias || []).forEach(function(cat) {
                (cat.endpoints || []).forEach(function(ep) {
                    html += '<tr><td>' + (ep.metodo || '--') + '</td><td>' + (ep.ruta || '--') + '</td><td>' + (cat.categoria || '--') + '</td></tr>';
                });
            });
            tbody.innerHTML = html || '<tr><td colspan="3" class="empty-msg">sin endpoints</td></tr>';
        }).catch(function(e) { mostrarToast('error cargando endpoints: ' + e.message, 'error'); });
    };
    window.ejecutarEndpointAdmin = function() {
        var path = (document.getElementById('endpoint-path-admin') || {}).value || '';
        var method = (document.getElementById('endpoint-method-admin') || {}).value || 'GET';
        var bodyRaw = (document.getElementById('endpoint-body-admin') || {}).value || '';
        var body = null;
        if (!path) { mostrarToast('indica un path', 'error'); return; }
        if (bodyRaw) {
            try { body = JSON.parse(bodyRaw); } catch (e) { mostrarToast('json invalido', 'error'); return; }
        }
        api(method, path, body).then(function(resp) {
            var out = document.getElementById('endpoint-respuesta-admin');
            if (out) out.textContent = JSON.stringify(resp, null, 2);
        }).catch(function(e) {
            var out = document.getElementById('endpoint-respuesta-admin');
            if (out) out.textContent = 'error: ' + e.message;
        });
    };
    window.detalleItem = function(id) {
        var panel = document.getElementById('n3-panel');
        if (!panel) return;
        panel.classList.add('show');
        panel.innerHTML = '<div class="n3-loading">detalle seleccionado: ' + id + '</div>';
    };

    document.addEventListener('DOMContentLoaded', init);
})();
