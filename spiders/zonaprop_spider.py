# spiders/argenprop_spider.py
import re
import scrapy
from urllib.parse import urljoin


class ArgenpropSpider(scrapy.Spider):
    name = "argenprop"
    allowed_domains = ["argenprop.com"]
    base_url = "https://www.argenprop.com"
    start_path = "/terrenos/venta/posadas"

    def __init__(self, max_pages: int | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages) if max_pages else None

    def start_requests(self):
        yield scrapy.Request(
            url=urljoin(self.base_url, self.start_path),
            callback=self.parse,
            meta={"page": 1},
        )

    def parse(self, response):
        cards = response.css(".listing__item")
        if not cards:
            self.logger.warning("⚠️ No se encontraron propiedades en %s", response.url)

        for i, card in enumerate(cards):
            moneda = card.css("p.card__price span.card__currency::text").get(default="").strip()
            valor = card.css("p.card__price::text").re_first(r"\d[\d\.\,]*", default="").strip()

            precio = f"{moneda} {valor}".strip() if valor else "Consultar precio"

            superficie = next(
                (
                    s.strip()
                    for s in card.css("ul.card__main-features li span::text").getall()
                    if "m²" in s
                ),
                "",
            )

            item = {
                "titulo": card.css("p.card__title--primary::text").get(default="").strip(),
                "descripcion": card.css("p.card__info::text").get(default="").strip(),
                "direccion": card.css("p.card__address::text").get(default="").strip(),
                "precio": precio,
                "superficie": superficie,
                "enlace": urljoin(self.base_url, card.css("a::attr(href)").get(default="")),
            }

            # Logging para debug de cada item extraído
            self.logger.info("✅ [%02d] Item extraído: %s – %s", i + 1, item["titulo"], item["precio"])
            yield item

        # Paginación
        current_page = response.meta["page"]
        next_rel = response.css("li.pagination__page-next a::attr(href)").get()

        if next_rel and (self.max_pages is None or current_page < self.max_pages):
            yield scrapy.Request(
                url=urljoin(self.base_url, next_rel),
                callback=self.parse,
                meta={"page": current_page + 1},
            )