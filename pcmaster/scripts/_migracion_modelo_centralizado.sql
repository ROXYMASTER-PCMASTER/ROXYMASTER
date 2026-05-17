-- migracion para modelo de asignacion centralizada v8.4
-- ejecutar con: sqlite3 roxymaster.db < este_archivo

-- 1. añadir columna liberacion_estimada a perfiles_roxy
alter table perfiles_roxy add column liberacion_estimada text;

-- 2. crear tabla de configuracion del planificador (valores dinamicos)
create table if not exists config_planificador (
    clave text primary key,
    valor text not null,
    descripcion text
);

insert or ignore into config_planificador (clave, valor, descripcion) values
    ('heartbeat_timeout', '35', 'segundos sin heartbeat para considerar pcbot desconectado'),
    ('match_ventana_post_heartbeat', '5', 'segundos de margen tras heartbeat para recibir eventos'),
    ('match_anticipacion_segundos', '5', 'cuanto antes incluir perfiles que se liberaran'),
    ('match_timeout_respuesta', '35', 'segundos para esperar respuesta del pcbot tras planificar');

-- 3. not null en estado de pedido_asignaciones si no existe
-- (ya existe, solo aseguramos consistencia)
-- los estados permitidos son: planificado, ejecutando, completado, fallido

-- 4. actualizar estados existentes de pedido_asignaciones que sean 'pendiente' a 'planificado'
update pedido_asignaciones set estado = 'planificado' where estado = 'pendiente' or estado is null;

-- 5. actualizar estados existentes de pedido_asignaciones que sean 'en_progreso' a 'ejecutando'
update pedido_asignaciones set estado = 'ejecutando' where estado = 'en_progreso';

-- 6. actualizar estados existentes de pedido_asignaciones que sean 'completado' a 'completado' (ya existe)
-- update pedido_asignaciones set estado = 'completado' where estado = 'terminado';

.print 'migracion completada.'