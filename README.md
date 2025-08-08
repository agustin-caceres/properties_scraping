# Scraping de Propiedades

> **Objetivo**
> Construir un pipeline reproducible que extraiga anuncios de *terrenos en venta* en la ciudad de **Posadas (Misiones, AR)**, transforme los datos y los aloje en una base **PostgreSQL** en la nube, con orquestación automatizada vía **GitHub Actions**.

---

## Índice

1. [Stack y dependencias](#stack-y-dependencias)
2. [Estructura del proyecto](#estructura-del-proyecto)
3. [Flujo de punta a punta](#flujo-de-punta-a-punta)
4. [Scraping - `argenprop_spider.py`](#scraping-argenprop_spiderpy)
5. [Limpieza & normalización - `ProcessFilePipeline`](#limpieza--normalización-processfilepipeline)
6. [Post‑proceso & carga - `postprocess.py`](#postproceso--carga-postprocesspy)
7. [Orquestador - `run_pipeline.py`](#orquestador-run_pipelinepy)
8. [Variables de entorno](#variables-de-entorno)
9. [Ejecución local](#ejecución-local)
10. [CI/CD con GitHub Actions](#cicd-con-github-actions)
11. [Campos extraídos](#campos-extraídos)
12. [Limitaciones conocidas](#limitaciones-conocidas)
13. [Próximos pasos](#próximos-pasos)

---

## Stack y dependencias

| Componente             | Versión       | Rol                                 |
| ---------------------- | ------------- | ----------------------------------- |
| **Python**             | 3.11          | Lenguaje principal                  |
| **Scrapy**             | 2.11+         | Web scraping asíncrono              |
| **pandas**             | 2.x           | Manipulación tabular y carga masiva |
| **SQLAlchemy**         | 2.x           | ORM / Core hacia PostgreSQL         |
| **psycopg2‑binary**    | 2.9           | Driver PostgreSQL                   |
| **scrapy‑user‑agents** | 0.1           | Rotación de *User‑Agent*            |
| **GitHub Actions**     | ubuntu‑latest | CI/CD programado                    |

Todas las dependencias se listan en **`requirements.txt`**.

---

## Estructura del proyecto

```text
scraping_properties/
├── .github/workflows/scraping.yml     # CI/CD semanal + manual
├── config.py                          # Ajustes Scrapy vía env vars
├── scrapy.cfg                       # Entry‐point Scrapy
├── runner/
│   └── run_pipeline.py                # Orquestador (scrape ➜ load)
├── pipelines/
│   ├── postprocess.py                 # Deduplica + upserts + carga
│   └── process_file.py                # Valida & normaliza cada Item
├── spiders/
│   └── argenprop_spider.py            # Spider focalizado en Posadas
├── outputs/
│   ├── data/                          # JSON exportado por Scrapy
│   └── logs/                          # Log por spider
├── logs/                              # Log general del pipeline
└── README.md                          # Este documento
```

---

## Flujo de punta a punta


1. **Scrapy** recolecta HTML de Argenprop.
2. **Pipeline** valida y normaliza cada anuncio.
3. **Feed exporter** almacena todo en un **JSON** único.
4. **Post‑processing** elimina duplicados internos y externos y lo inserta en **PostgreSQL**.

---

## Scraping - `argenprop_spider.py`

| Aspecto             | Detalle                                                            |
| ------------------- | ------------------------------------------------------------------ |
| **URL seed**        | `https://www.argenprop.com/terrenos/venta/posadas`                 |
| **Paginación**      | Selector `li.pagination__page-next a[href]` (`max_pages` opcional) |
| **Anti‑baneos**     | Rotación de *User‑Agent* + `DOWNLOAD_DELAY` configurable           |
| **Logging**         | Item‑level (`✅ Item extraído … precio`) y resumen                  |

---

## Limpieza & normalización - `ProcessFilePipeline`

* Asegura presencia de **`titulo`** y **`precio`**; descarta en caso contrario.
* Normaliza:

  * **`titulo`, `direccion`, `descripcion`** → `.strip()`
  * **`precio`** → `float` + **`moneda`** (`USD` / `ARS`)
  * **`lat`, `lon`** → `float` o `None` (sin descartar el item)
* Loguea descartes para auditoría.

---

## Post‑proceso & carga - `postprocess.py`

| Paso | Qué hace                                                                      |
| ---- | ----------------------------------------------------------------------------- |
| 1    | Lee el JSON → `pandas.DataFrame`                                              |
| 2    | Valida columnas mínimas                                                       |
| 3    | **Deduplicación interna** por (`titulo`, `direccion`, `precio`)               |
| 4    | Genera PK `uuid` y `fecha_creacion`                                           |
| 5    | **Deduplicación externa** contra la tabla `properties` (clave única `enlace`) |
| 6    | Inserta en lotes (500 filas) con `method="multi"`                             |

Si la tabla no existe, `if_exists="append"` la crea automáticamente.

---

## Orquestador - `run_pipeline.py`

* Ejecuta uno o varios spiders (`scrapy crawl …`) con timeout y argumentos extra.
* Limpia el JSON previo para evitar duplicaciones.
* Verifica si hubo datos nuevos; si **no** los hubo, salta la carga.
* Integra **logging** granular en `logs/full_pipeline.log`.
* API flexible:

  ```bash
  python -m runner.run_pipeline argenprop --timeout 300 -v
  ```
* Integrable en otros proyectos: `from runner.run_pipeline import run_pipeline`.

---

## Variables de entorno

| Variable              | Ejemplo                                       | Descripción          |
| --------------------- | --------------------------------------------- | -------------------- |
| `DB_URL`              | `postgresql+psycopg2://user:pwd@host:5432/db` | Conexion cloud       |
| `FEED_URI`            | `./outputs/data/properties_output.json`       | Ruta JSON (override) |
| `LOG_FILE`            | `./outputs/logs/argenprop.log`                | Log por spider       |
| `CONCURRENT_REQUESTS` | `8`                                           | Paralelismo Scrapy   |
| `DOWNLOAD_DELAY`      | `1.0`                                         | Delay entre requests |

Se cargan automáticamente con `dotenv`.

---

## Ejecución local

```bash
# 1) Crear y activar venv, luego:
pip install -r requirements.txt

# 2) Configurar .env (al menos DB_URL)

# 3) Correr 1 página (dry‑run)
python -m runner.run_pipeline argenprop -a max_pages=1 --dry-run -v

# 4) Correr 2 páginas e insertar en DB
python -m runner.run_pipeline argenprop -a max_pages=2 --timeout 300 -v
```

---

## CI/CD con GitHub Actions

Archivo **`.github/workflows/scraping.yml`**:

| Paso         | Acción                                                            |
| ------------ | ----------------------------------------------------------------- |
| Checkout     | Clona repo                                                        |
| Cache pip    | Acelera installs                                                  |
| Setup Python | 3.11                                                              |
| Install deps | `pip install -r requirements.txt`                                 |
| `.env`       | Inyecta `DB_URL` desde secreto                                    |
| **Pipeline** | `python -m runner.run_pipeline argenprop --timeout 120 --verbose` |
| Artefactos   | Sube logs + JSON                                                  |

Cron: `0 10 * * 1` → todos los lunes 07:00 ART.

---

## Campos extraídos

| Campo            | Tipo                  | Ejemplo                           |
| ---------------- | --------------------- | --------------------------------- |
| `id`             | `UUID`                | `2f7a…`                           |
| `fecha_creacion` | `timestamp`           | `2025-08-07T23:09:12Z`            |
| `titulo`         | `text`                | "Terreno en Altos de Bella Vista" |
| `direccion`      | `text`                | "Altos de Bella Vista, Posadas"   |
| `descripcion`    | `text`                | "Oportunidad única…"              |
| `precio`         | `numeric`             | `35000.0`                         |
| `moneda`         | `varchar(3)`          | `USD`                             |
| `superficie`     | `varchar`             | `600 m²`                          |
| `enlace`         | `varchar(500) UNIQUE` | URL absoluta                      |
| `lat`            | `float`               | `-27.362`                         |
| `lon`            | `float`               | `-55.900`                         |

---

## Limitaciones conocidas

1. **Coordenadas no siempre disponibles** → se almacenan como `NULL`.
2. La estructura HTML puede cambiar; se mitiga con selectores robustos y logging de fallos.
3. El pipeline descarta items sin `titulo` o `precio`.
4. Cargas masivas adicionales requerirán paginar más de 2 páginas.

---
