# backup de guardar_perfil_roxy original antes de cambiarlo a reemplazar_perfiles_roxy
# fecha: 2026-05-10 09:49

def guardar_perfil_roxy_original(usuario_id: int, computadora_id: str, nombre: str, hash_perfil: str, workspace_id: int):
    """guarda o reemplaza un perfil roxy en la tabla perfiles_roxy."""
    with get_db() as conn:
        conn.execute("""
            insert or replace into perfiles_roxy (usuario_id, computadora_id, nombre, hash, workspace_id, ultima_sincronizacion)
            values (?, ?, ?, ?, ?, current_timestamp)
        """, (usuario_id, computadora_id, nombre, hash_perfil, workspace_id))