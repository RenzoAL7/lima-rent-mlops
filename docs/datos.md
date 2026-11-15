# Datos

## Fuentes

| Fuente | Qué aporta | Frecuencia | Uso en el proyecto |
|---|---|---|---|
| [Infocasas](https://www.infocasas.com.pe) | Avisos de alquiler de departamentos en Lima Metropolitana y Callao | Semanal (scraping) | Entrenamiento, ground truth semanal y drift |
| [BCRP](https://estadisticas.bcrp.gob.pe) | Tipo de cambio venta (`PD04640PD`), precio de venta por m² y PER de alquiler por distrito | Diaria / trimestral | Convertir USD a soles; contexto de mercado en la página Drift |
| [INEI, ENAHO módulo 100](https://proyectos.inei.gob.pe/microdatos/) | Alquiler mensual que pagan los hogares (`P105B`) | Anual | Contexto: lo que se paga frente a lo que se pide |

Properati (BigQuery público), Urbania y Adondevivir se evaluaron y se descartaron: el dataset de Properati dejó de ser accesible y los otros dos portales bloquean clientes automáticos.

### Infocasas

`sources/infocasas.py` lee el JSON que Next.js incrusta en cada página de resultados (`__NEXT_DATA__`). No ejecuta JavaScript ni usa APIs privadas.

Reglas del scraper:

- Revisa `robots.txt` antes de empezar y se detiene si la ruta está prohibida.
- Espera 4 segundos entre páginas (`SCRAPE_DELAY_SECONDS`) y reintenta con espera creciente.
- Se identifica con un User-Agent que enlaza a este repositorio.
- Corre una vez por semana y como máximo `SCRAPE_MAX_PAGES` páginas.
- Guarda solo campos numéricos y de ubicación: id, fechas, distrito, latitud y longitud, precio y moneda, mantenimiento, área, dormitorios, baños, cocheras, piso, amoblado y estado.
- **No guarda** título, descripción, fotos, nombre del anunciante ni datos de contacto.

**Aviso sobre términos de uso.** Los términos de Infocasas restringen la reutilización de su contenido. Este es un proyecto educativo y no comercial. Los avisos no se republican: el bucket es privado y el dashboard muestra solo agregados y predicciones del modelo. Si el sitio se hace público con tráfico real, conviene pedir autorización a Infocasas o cambiar de fuente.

### BCRP

`sources/bcrp.py` usa la API pública de series estadísticas.

- **Tipo de cambio:** serie diaria. Se descarga de forma incremental desde 2020 y los feriados se cubren con el último valor (`merge_asof`).
- **Alquiler por m²:** para los 12 distritos que publica el BCRP, se calcula como venta por m² ÷ PER ÷ 12. Es la referencia "oficial" que se compara en la página Drift con la mediana de los avisos.

### ENAHO

`sources/enaho.py` descarga el zip del módulo 100 de cada año y filtra los hogares de Lima y Callao que alquilan (`P105A = 1`). Se queda con el pago mensual (`P105B`), el factor de expansión y unas pocas variables de la vivienda.

## Lago de datos

Hay un bucket de OCI Object Storage (`lima-rent-mlops`, privado), al que se accede por la API compatible con S3. En local, la misma estructura vive en una carpeta (`DATA_URI=data`) o en SeaweedFS con Docker Compose.

```
bronze/infocasas/fecha=AAAA-MM-DD/listings.parquet   respuesta del portal, aplanada
silver/listings.parquet                              historial limpio (primera y última vez visto)
silver/fx_usd_pen.parquet                            tipo de cambio diario
silver/bcrp_alquiler_m2.parquet                      alquiler por m² del BCRP, por distrito y trimestre
silver/enaho_alquileres.parquet                      alquileres pagados según la ENAHO
models/champion/{p10,p50,p90}.txt, meta.json         modelo en producción (lo carga la API)
models/champion/reference.parquet                    muestra de entrenamiento para medir drift
models/history.json                                  cada reentrenamiento y su decisión
monitoring/last_run.json                             resumen de la última corrida
monitoring/quality.parquet                           avisos descartados por regla, por semana
monitoring/performance.parquet                       MAE / MAPE / cobertura por semana y distrito
monitoring/drift.parquet                             PSI y KS por variable y semana
monitoring/target_drift.parquet                      precio por m² por semana y distrito
monitoring/predictions/semana=AAAA-Www.parquet       predicción vs precio real de los avisos nuevos
mlflow-artifacts/                                    artefactos del servidor de MLflow
```

## Limpieza (bronze → silver)

`processing/clean.py` descarta y cuenta cada regla, para que la página Calidad muestre por qué se perdió cada aviso:

- Avisos que no son alquiler de departamento, que no tienen precio o que están fuera de Lima Metropolitana y Callao.
- Valores fuera de rango: área de 15 a 600 m², precio de S/ 300 a S/ 60 000, precio por m² de S/ 5 a S/ 250, y hasta 8 dormitorios y 8 baños.
- Duplicados por `id`.

Los precios en dólares se pasan a soles con el tipo de cambio del día de publicación. El esquema estricto de silver se valida con Pandera.

## Ground truth semanal

Un aviso nuevo es uno que no aparecía en silver. Antes de usarlo para entrenar, el champion lo predice: el precio publicado es la "verdad" contra la que se miden el error y la cobertura del intervalo del 80 %. Así el desempeño se mide siempre sobre datos que el modelo no vio.
