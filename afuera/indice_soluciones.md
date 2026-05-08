
## [2026-05-07 19:07:18] Unificacion de carpeta publica

**Problema:** Los archivos estaticos se servian desde scripts/publico (ruta relativa), pero los HTML reales estaban en pcmaster/publico. Esto provocaba errores 404 que inyectaban HTML mal formado y rompian la ejecucion de scripts.

**Solucion aplicada:**
- Se cambio la ruta en server.py a absoluta: C:/Users/PCMASTER/Desktop/roxymaster/pcmaster/publico.
- Se eliminaron las carpetas sobrantes scripts/publico y portal_publico.
- Se aseguro la presencia de dashboard.css para evitar 404.

**Archivos modificados:** server.py
**Archivos eliminados:** scripts/publico/ (todo el contenido), portal_publico/
**Ruta definitiva de archivos estaticos:** C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\publico\

**Instrucciones para el agente:** Reiniciar el servidor despues de aplicar estos cambios.

## [2026-05-07 19:09:08] Unificacion de carpeta publica

**Problema:** Los archivos estaticos se servian desde scripts/publico (ruta relativa), pero los HTML reales estaban en pcmaster/publico. Esto provocaba errores 404 que inyectaban HTML mal formado y rompian la ejecucion de scripts, impidiendo que los modales de "Agregar perfil" y "Crear orden" funcionaran.

**Solucion aplicada:**
- Se cambio la ruta en server.py a absoluta: C:/Users/PCMASTER/Desktop/roxymaster/pcmaster/publico.
- Se eliminaron las carpetas sobrantes scripts/publico y portal_publico.
- Se aseguro la presencia de dashboard.css para evitar 404.

**Archivos modificados:** server.py
**Archivos eliminados:** scripts/publico/ (todo el contenido), portal_publico/
**Ruta definitiva de archivos estaticos:** C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\publico\

**Instrucciones para el agente:** Reiniciar el servidor despues de aplicar estos cambios.

## [2026-05-07 19:19:49] Corrección de ImportError y unificación de estáticos

**Problema:** El servidor no arrancaba debido a ImportError: cannot import name 'obtener_tasa_kbt_pen'. La función no existía en 	okenomics.py. Además, la carpeta de archivos estáticos se servía con ruta relativa, provocando 404 en los paneles.

**Solucion:**
- Se creó la función obtener_tasa_kbt_pen en 	okenomics.py que calcula la tasa KBT/PEN según la fórmula económica P_token = (G * beta) / K_total.
- Se verificó y corrigió la importación en pi_public_finanzas.py.
- Se cambió server.py para usar ruta absoluta C:/Users/PCMASTER/Desktop/roxymaster/pcmaster/publico al montar /publico.
- Se eliminaron carpetas duplicadas (scripts/publico, portal_publico) en una ejecución anterior.

**Archivos modificados:** 	okenomics.py (nueva función), pi_public_finanzas.py (import), server.py (ruta estática).
**Archivos de respaldo:** 	okenomics.py.backup_20260507_191948, pi_public_finanzas.py.backup_20260507_191948, server.py.backup_*.
**Registro creado para referencia de otros agentes IA.**

