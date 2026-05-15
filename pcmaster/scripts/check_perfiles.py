from db import ejecutar_sql
perfiles = ejecutar_sql("SELECT hash, activo, pcbot_id FROM perfiles_roxy WHERE pcbot_id='PCWILMER'")
print('Perfiles en BD:', perfiles)
print('Total:', len(perfiles) if perfiles else 0)
