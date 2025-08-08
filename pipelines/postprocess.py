"""
pipelines/postprocess.py
========================
Carga en bloque los datos limpiados por Scrapy a PostgreSQL.

• Lee el JSON exportado por Scrapy («properties_output.json»).
• Valida columnas mínimas.
• Elimina duplicados internos y externos (ya existentes en DB).
• Inserta en la tabla «properties» con pandas → SQLAlchemy.
• Deja trazabilidad con logging.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Final

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# ─────────────── Setup logging + .env ───────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
load_dotenv()

# ───────────────────────── Helpers ─────────────────────────
def _get_engine():
    db_url: Final[str | None] = os.getenv("DB_URL")
    if not db_url:
        raise EnvironmentError("❌ Falta DB_URL en variables de entorno")
    return create_engine(db_url, pool_pre_ping=True, echo=False)


def _validate_columns(df: pd.DataFrame) -> None:
    required = {"titulo", "precio"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {', '.join(missing)}")


def _deduplicate_internal(df: pd.DataFrame) -> pd.DataFrame:
    subset = [c for c in ("titulo", "direccion", "precio") if c in df.columns]
    return df.drop_duplicates(subset=subset, keep="first")


def _deduplicate_external(df: pd.DataFrame, engine, table_name: str) -> pd.DataFrame:
    """
    Quita filas cuyo «enlace» ya exista en la tabla destino.
    """
    if "enlace" not in df.columns:
        return df  # nada que comparar

    # Traer enlaces existentes (solo columna clave, indexados)
    with engine.connect() as conn:
        existing = pd.read_sql(
            text(f"SELECT enlace FROM {table_name}"),
            conn,
            columns=["enlace"],
        )
    if existing.empty:
        return df

    df_filtered = df[~df["enlace"].isin(existing["enlace"])]
    removed = len(df) - len(df_filtered)
    if removed:
        logger.info("🔎 %s duplicados externos filtrados por «enlace»", removed)
    return df_filtered

# ─────────────────────── Carga principal ───────────────────────
def load(json_path: str | Path, *, if_exists: str = "append") -> None:
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo JSON no encontrado: {path}")

    df = pd.read_json(path)
    if df.empty:
        logger.warning("El JSON está vacío; nada que insertar.")
        return

    _validate_columns(df)
    df = _deduplicate_internal(df)

    # ── Generar columnas de la tabla que faltan ──
    if "id" not in df.columns:
        df["id"] = [uuid.uuid4() for _ in range(len(df))]
    if "fecha_creacion" not in df.columns:
        df["fecha_creacion"] = datetime.utcnow()

    # ── Mantener solo las columnas que existen en la tabla ──
    allowed_cols = {
        "id", "fecha_creacion",
        "titulo", "descripcion", "direccion",
        "precio", "moneda", "superficie",
        "enlace", "lat", "lon",
    }
    df = df[[c for c in df.columns if c in allowed_cols]]

    engine = _get_engine()
    table_name = os.getenv("DB_TABLE", "properties")

    # ── Filtrado de duplicados externos ──
    df = _deduplicate_external(df, engine, table_name)
    if df.empty:
        logger.info("🟢 No hay registros nuevos para insertar (todo duplicado).")
        return

    try:
        df.to_sql(
            table_name,
            con=engine,
            if_exists=if_exists,
            index=False,
            chunksize=500,
            method="multi",
        )
        logger.info("✅ Cargadas %s filas únicas en «%s».", len(df), table_name)
    except SQLAlchemyError as err:
        logger.error("❌ Error al insertar en PostgreSQL: %s", err)
        raise

# ───────────────────────── CLI opcional ─────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carga JSON -> PostgreSQL")
    parser.add_argument(
        "json",
        nargs="?",
        default="outputs/data/properties_output.json",
        help="Ruta al JSON exportado por Scrapy",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Reemplaza la tabla destino en lugar de append",
    )
    args = parser.parse_args()

    load(args.json, if_exists="replace" if args.replace else "append")