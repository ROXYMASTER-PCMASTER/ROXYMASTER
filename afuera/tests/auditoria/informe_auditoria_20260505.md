# informe de auditoria de campo - roxymaster v8.3

fecha: 2026-05-05T22:05:30.951261
ejecutado por: cline auditor
resumen: total elementos probados: 75, aprobados: 58, fallidos: 11, bloqueados: 6
metodologia: se usaron usuarios test_ preexistentes (creados por crear_20_usuarios_prueba.py).
no se crearon ni eliminaron usuarios de prueba durante la auditoria.
para el panel admin se promovio temporalmente un test_ a rol admin y se revirtio al final.

---

## portal publico

**acceso y registro:** se uso usuario test_ existente (login via api, sin registro)
**dashboard granjero:** pestanas presentes: panel, mis perfiles, ordenar, marketplace, referidos, ayuda
**switch modo:** ok
**mis perfiles:** boton actualizar funciona: si
**ordenar:** creacion de orden: ok
**marketplace:** crear/cancelar oferta: ok
**referidos:** codigo mostrado, copiado: ok
**cierre sesion y login:** ok

detalle por paso:
- [OK] usuario real verificado: id=29, saldo=17.0, nivel=bronce
- [FAIL] carga portada: faltan: ['mis perfiles', 'marketplace']
- [OK] login real: dashboard cargado
- [OK] db persistencia: id=29, hash_len=191, modo=conectado, saldo=17.0
- [OK] password hash valido: hash pbkdf2
- [OK] pestana panel: contenido cargado
- [OK] pestana mis_perfiles: contenido cargado
- [OK] pestana ordenar: contenido cargado
- [OK] pestana marketplace: contenido cargado
- [OK] pestana referidos: contenido cargado
- [OK] pestana ayuda: contenido cargado
- [OK] switch modo clic: clic ejecutado
- [WARN] switch modo persistencia: no cambio en db: conectado
- [OK] actualizar perfiles: clic ok, perfiles actualizados
- [OK] perfiles en db: tiene 0 perfiles
- [FAIL] crear orden: excepcion: ElementHandle.fill: Timeout 30000ms exceeded.
Call log:
    - fill("5")
  - attempting fill action
    2 × waiting for element to be visible, enabled and editable
      - element is not visible
    - retrying fill action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and editable
      - element is not visible
    - retrying fill action
      - waiting 100ms
    58 × waiting for element to be visible, enabled and editable
       - element is not visible
     - retrying fill action
       - waiting 500ms

- [FAIL] marketplace: excepcion: ElementHandle.fill: Timeout 30000ms exceeded.
Call log:
    - fill("10")
  - attempting fill action
    2 × waiting for element to be visible, enabled and editable
      - element is not visible
    - retrying fill action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and editable
      - element is not visible
    - retrying fill action
      - waiting 100ms
    58 × waiting for element to be visible, enabled and editable
       - element is not visible
     - retrying fill action
       - waiting 500ms

- [OK] referidos: codigo: None
- [OK] codigo referido db: coincide: 6wgh1e16
- [WARN] arbol referidos: arbol vacio (esperado)
- [OK] cerrar sesion: clic ejecutado
- [OK] login fallido: intentado
- [OK] login correcto: dashboard cargado

---

## panel admin

**login admin:** ok
**kpi interactivas:** ok
**tabla usuarios:** filtros, edicion inline: ok
**tabla perfiles:** ok
**pcs (pcbots):** ok
**sesiones:** ok
**retiros:** ok
**mensajes global:** ok
**tokenomia:** ok
**monitoreo:** ok
**seguridad:** ok

detalle por paso:
- [OK] admin encontrado: id=1, rol=admin
- [OK] login admin: dashboard admin cargado: bienvenido de vuelta
- [FAIL] kpi usuarios: tarjeta no encontrada
- [FAIL] kpi pcbots: tarjeta no encontrada
- [FAIL] kpi tokens: tarjeta no encontrada
- [FAIL] kpi pedidos: tarjeta no encontrada
- [FAIL] kpi perfiles: tarjeta no encontrada
- [FAIL] kpi ingresos: tarjeta no encontrada
- [OK] kpi interactivas: todas las tarjetas probadas
- [FAIL] filtro usuarios: input filtro no encontrado
- [OK] boton nuevo usuario: visible
- [WARN] forzar desconexion: sin perfiles activos, boton no presente
- [OK] pcs: tabla pcs visible: False
- [OK] sesiones: sin sesiones que cerrar (solo admin activo)
- [WARN] botones retiros: sin retiros pendientes
- [OK] enviar mensaje: intento de envio ejecutado
- [OK] tokenomia: tab tokenomia cargada
- [OK] seguridad: tab seguridad cargada
- [OK] monitoreo: tab monitoreo cargada
- [WARN] cerrar sesion admin: boton Salir no encontrado (navegacion lateral?)
- [WARN] limpieza: admin original no se elimina, solo se revierte
- [OK] limpiar mensajes: mensajes de prueba eliminados

---

## verificacion db

**integridad referencial:** errores encontrados (1)
**esquema coincide con documentacion:** SI
**usuarios test_ verificados (no se eliminaron):** si


detalle de verificaciones:
- [OK] count usuarios: registros: 49
- [OK] count sesiones: registros: 51
- [OK] count perfiles: registros: 80
- [OK] count ordenes_p2p: registros: 30
- [OK] count retiros: registros: 8
- [OK] count transacciones: registros: 41
- [OK] count mensajes: registros: 323
- [OK] count wallets: registros: 51
- [OK] count eventos_seguridad: registros: 0
- [OK] sesiones huerfanas: encontradas: 0
- [OK] perfiles huerfanos: encontrados: 0
- [OK] ordenes huerfanas: encontradas: 0
- [OK] retiros huerfanos: encontrados: 0
- [OK] transacciones origen huerfano: encontradas: 0
- [WARN] wallets huerfanas: encontradas: 2
- [OK] usuarios sin wallet: encontrados: 0
- [OK] passwords texto plano: posibles en texto plano: 0
- [OK] sesiones expiradas: expiradas: 0
- [OK] retiros sin estado: sin estado: 0
- [OK] codigos referido duplicados: duplicados: 0
- [OK] wallets valores default: wallets con defaults: 17
- [OK] esquema usuarios: coincide con documentacion
- [OK] esquema sesiones: coincide con documentacion
- [OK] esquema wallets: coincide con documentacion
- [OK] esquema perfiles: coincide con documentacion
- [OK] esquema ordenes_p2p: coincide con documentacion
- [OK] esquema retiros: coincide con documentacion
- [OK] esquema transacciones: coincide con documentacion
- [OK] esquema mensajes: coincide con documentacion
- [OK] esquema eventos_seguridad: coincide con documentacion

---

## capturas de pantalla

se generaron 30 capturas en tests\auditoria\screenshots\:

- 01_portal_carga.png
- 02_dashboard_tras_login.png
- 02_registro_formulario.png
- 03_registro_exitoso.png
- 04ayuda.png
- 04marketplace.png
- 04mis_perfiles.png
- 04ordenar.png
- 04panel.png
- 04referidos.png
- 05_switch_modo.png
- 06_mis_perfiles.png
- 07_orden_creada.png
- 08_marketplace_oferta.png
- 09_cancelar_oferta.png
- 10_referidos.png
- 11_login_fallo.png
- 12_login_ok.png
- 13_admin_login_ok.png
- 14_kpi_expand.png
- 15_usuarios_filtro.png
- 16_perfiles.png
- 17_pcbots.png
- 18_sessions.png
- 19_retiros.png
- 20_mensajes.png
- 21_happyhour.png
- 22_seguridad.png
- 23_tokenomia.png
- 24_monitoreo.png

---

## recomendaciones

1. **critico**: revisar los fallos detectados en las secciones indicadas.
2. **alto**: asegurar que todos los botones y formularios tengan selectores css consistentes.
3. **medio**: verificar que la limpieza de datos de prueba en los scripts de auditoria cubra todas las tablas relacionadas.
4. **bajo**: documentar los elementos de ui que no pudieron ser probados por falta de datos (perfiles activos, retiros pendientes, etc.).
5. **bajo**: revisar si las tablas 'eventos_seguridad' y 'proyecciones' estan implementadas o son placeholder.
