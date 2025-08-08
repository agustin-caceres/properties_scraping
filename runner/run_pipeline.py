"""
runner/run_pipeline.py - Orquestador del scraping de propiedades (Ejercicio 3)
======================================================================

• Ejecuta el spider `zonaprop` (y los que agregues) con timeout, verbose,
  dry-run, etc.
• Valida que se haya generado `properties_output.json`.
• Si hay datos nuevos y NO es dry-run, dispara `pipelines.load_data`
  para cargar en PostgreSQL o guardar un CSV en la nube.
• Puede importarse como función  ➜  run_pipeline(["zonaprop"], timeout=300)
  o ejecutarse desde CLI        ➜  python -m runner.run_pipeline zonaprop
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

__all__ = ["run_pipeline", "cli_main"]

# ──────────────────────────── Rutas y logger ────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "data"
OUTPUT_FILE = OUTPUTS_DIR / "properties_output.json"

logging.getLogger().setLevel(logging.WARNING)          # default global level
logger = logging.getLogger("scraping_properties.runner")


# ───────────────────────────── Helpers internos ──────────────────────────
def _configure_logging(log_file: Path | None, verbose: bool) -> None:
    """Inicializa logging SOLO para el orquestador (no afecta a Scrapy)."""
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  [%(levelname)s]  %(message)s",
        handlers=handlers,
        force=True,
    )


def _run_subprocess(cmd: List[str], timeout: int | None) -> bool:
    """Ejecuta *cmd* dentro de PROJECT_ROOT, devolviendo True si exit-code 0."""
    try:
        subprocess.run(cmd, check=True, timeout=timeout, cwd=PROJECT_ROOT)
        return True
    except subprocess.TimeoutExpired:
        logger.error("⏱️  Timeout (%ss) → %s", timeout, " ".join(cmd))
    except subprocess.CalledProcessError as exc:
        logger.error("⚠️  Exit %s → %s", exc.returncode, " ".join(cmd))
    return False


def _clean_output_file() -> None:
    """Elimina el JSON previo para evitar concatenaciones inválidas."""
    if OUTPUT_FILE.exists():
        try:
            OUTPUT_FILE.unlink()
            logger.debug("🗑️  Removed previous output: %s", OUTPUT_FILE)
        except Exception as err:  # pragma: no cover
            logger.warning("No se pudo eliminar %s – %s", OUTPUT_FILE, err)


def _run_spider(spider: str, timeout: int | None, extra_args: List[str]) -> bool:
    """Lanza `scrapy crawl spider …` con limpieza previa de outputs."""
    logger.info("🚀 Spider start: %s", spider)
    _clean_output_file()
    t0 = time.time()
    ok = _run_subprocess(["scrapy", "crawl", spider, *extra_args], timeout)
    logger.info("✅ Spider %s %s (%.1fs)", spider, "OK" if ok else "ERR", time.time() - t0)
    return ok


def _has_new_data() -> bool:
    """True si properties_output.json existe y contiene al menos un ítem."""
    if not OUTPUT_FILE.exists():
        return False
    try:
        data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        return bool(data)
    except json.JSONDecodeError as err:
        logger.warning("JSON inválido %s – %s", OUTPUT_FILE, err)
        return False


def _run_postproc(dry_run: bool) -> bool:
    """
    Si *dry_run* es False y hay datos nuevos, ejecuta `pipelines.load_data`
    para volcar los resultados en PostgreSQL o CSV.
    """
    if dry_run:
        logger.info("🟡 DRY-RUN → skip postproc")
        return True
    if not _has_new_data():
        logger.info("🟢 No new data → skip postproc")
        return True

    logger.info("🚀 Post-processing (load_data)")
    t0 = time.time()
    try:
        load_mod = importlib.import_module("pipelines.postprocess")
        load_mod.load(OUTPUT_FILE)          
        logger.info("✅ Post-proc OK (%.1fs)", time.time() - t0)
        return True
    except Exception as err:
        logger.error("❌ Post-proc error: %s", err)
        return False


# ───────────────────────────── API pública ──────────────────────────────
def run_pipeline(
    spiders: List[str],
    *,
    timeout: int | None = None,
    dry_run: bool = False,
    log_file: str | Path | None = Path("logs/full_pipeline.log"),
    verbose: bool = False,
    extra_args: List[str] | None = None,
) -> Dict[str, bool]:
    """
    Ejecuta el pipeline completo para cada *spider* indicado.

    Parameters
    ----------
    spiders      : lista de nombres de spiders (ej. ["zonaprop"])
    timeout      : límite en segundos para cada subproceso
    dry_run      : solo scraping, sin carga a DB/CSV
    log_file     : ruta de log (usa "-" para desactivar archivo)
    verbose      : modo DEBUG si True
    extra_args   : argumentos extra para `scrapy crawl` (ej. ["-a", "pages=2"])

    Returns
    -------
    dict[str, bool]  Mapeo spider → éxito global (scraping + postproc)
    """
    if isinstance(log_file, str):
        log_file = None if log_file == "-" else Path(log_file)
    _configure_logging(log_file, verbose)
    extra_args = extra_args or []

    results: Dict[str, bool] = {}
    for spider in spiders:
        logger.info("════════ PIPELINE: %s ════════", spider.upper())
        ok_scrape = _run_spider(spider, timeout, extra_args)
        ok_post   = _run_postproc(dry_run) if ok_scrape else False
        results[spider] = ok_scrape and ok_post
    return results


# ─────────────────────────────── CLI ───────────────────────────────
def cli_main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Scraping + carga de propiedades")
    parser.add_argument("spiders", nargs="+", help="zonaprop …")
    parser.add_argument("-a", dest="extra", nargs=argparse.REMAINDER,
                        help="Args extra para scrapy (ej. -a pages=2)")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-file", default="logs/full_pipeline.log")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    res = run_pipeline(
        spiders=args.spiders,
        timeout=args.timeout,
        dry_run=args.dry_run,
        log_file=args.log_file,
        verbose=args.verbose,
        extra_args=args.extra or [],
    )
    sys.exit(0 if all(res.values()) else 1)


if __name__ == "__main__":  # pragma: no cover
    cli_main()