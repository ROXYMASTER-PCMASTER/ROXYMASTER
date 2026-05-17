from db import ejecutar_sql
r = ejecutar_sql("SELECT url, frases_pool, ultimo_analisis FROM contextos_streamer WHERE url LIKE '%kick%'")
print('Registros en contextos_streamer:', r)
