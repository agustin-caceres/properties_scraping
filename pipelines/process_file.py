import logging
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ProcessFilePipeline:
    """
    Valida y normaliza los items extraídos por el spider.
    - Verifica campos obligatorios
    - Limpia strings
    - Convierte precio a número flotante y agrega moneda
    - Normaliza coordenadas, cuando existen
    """

    # ───────────────────────────── Public API ─────────────────────────────
    def process_item(self, item, spider):
        try:
            # ────────────────────────── Validaciones ──────────────────────────
            if not item.get("titulo") or not item.get("precio"):
                raise ValueError("Faltan campos obligatorios: 'titulo' o 'precio'")

            # ────────────────────────── Normalizaciones ───────────────────────
            item["titulo"] = item["titulo"].strip()

            # Precio → float  + moneda
            item["precio"], item["moneda"] = self._parse_precio(item["precio"])

            # Dirección (opcional)
            if item.get("direccion"):
                item["direccion"] = item["direccion"].strip()

            # Coordenadas (opcionales y robustas)
            item["lat"], item["lon"] = self._parse_coords(
                item.get("lat"), item.get("lon")
            )

            return item

        except Exception as e:
            logger.warning(f"❌ Item descartado: '{item.get('titulo', 'sin título')}' - {e}")

            raise DropItem(f"Item descartado: {e}")

    # ───────────────────────────── Helpers ────────────────────────────────
    def _parse_precio(self, raw_precio: str) -> tuple[float, str]:
        """
        Convierte 'USD 35.000' o '$ 2.500.000' a (35000.0, 'USD') o (2500000.0, 'ARS')
        """
        if not isinstance(raw_precio, str):
            raise ValueError("Formato de precio inválido (no string)")

        moneda = "ARS"  # default
        if "USD" in raw_precio.upper():
            moneda = "USD"

        precio_limpio = (
            raw_precio.replace("$", "")
            .replace("USD", "")
            .replace(".", "")
            .replace(",", "")
            .strip()
        )

        try:
            precio_float = float(precio_limpio)
        except ValueError:
            raise ValueError(f"Precio inválido: {raw_precio}")

        return precio_float, moneda

    def _parse_coords(self, lat_raw, lon_raw) -> tuple[float | None, float | None]:
        """
        Devuelve (lat, lon) como floats o (None, None) si no son válidas.
        """
        try:
            lat = float(lat_raw) if lat_raw not in (None, "", "-") else None
            lon = float(lon_raw) if lon_raw not in (None, "", "-") else None
            return lat, lon
        except (ValueError, TypeError):
            # Coordenadas malformateadas → descartar solo coords, no todo el item
            logger.debug("Coordenadas inválidas; se establecen a None")
            return None, None