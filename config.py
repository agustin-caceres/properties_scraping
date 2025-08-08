import os
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

# ──────────────── Parámetros generales ────────────────
BOT_NAME = "scraping_properties"
SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

ROBOTSTXT_OBEY = False
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", 8))
DOWNLOAD_DELAY      = float(os.getenv("DOWNLOAD_DELAY", 1.0))
COOKIES_ENABLED     = True
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")

# ──────────────── Feed de salida ────────────────
FEEDS = {
    os.getenv("FEED_URI", "./outputs/data/properties_output.json"): {
        "format": "json",
        "encoding": "utf8",
        "indent": 4,
        "ensure_ascii": False,
    }
}

# ──────────────── Logs ────────────────
LOG_FILE = os.getenv("LOG_FILE", "./outputs/logs/zonaprop.log")

# ──────────────── User-Agent aleatorio ────────────────
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy_user_agents.middlewares.RandomUserAgentMiddleware": 400,
}

# ──────────────── Pipeline de limpieza ────────────────
ITEM_PIPELINES = {
    "pipelines.process_file.ProcessFilePipeline": 300,
}