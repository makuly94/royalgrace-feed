#!/usr/bin/env python3
"""
Конвертер: Google Merchant feed (Royal Grace) -> YML feed
в той же структуре, что и рабочий фид abertime (customer_23732_bono.xml).

Запуск:
    pip install lxml requests
    python google_to_yml.py                 # скачает исходный фид и создаст feed_yml.xml
    python google_to_yml.py source.xml      # или возьмёт локальный файл

Для автообновления поставьте на cron (раз в час/сутки) и отдавайте
feed_yml.xml через ваш веб-сервер — это и будет новая ссылка на фид.
"""
import re
import sys
from datetime import datetime

import requests
from lxml import etree

# ---------------- НАСТРОЙКИ ----------------
SRC = ("https://royalgrace.com.ua/marketplace-integration/google-feed/"
       "235e932fb988b8cb20f1bd6cba5caa83?langId=3")
OUT = "feed_yml.xml"

SHOP_URL = "https://royalgrace.com.ua/"
SHOP_NAME = "Royal Grace"
COMPANY = "Royal Grace"
PHONE = ""                 # впишите телефон, если нужен (тег <phone>)
DEFAULT_VENDOR = "Royal Grace"   # для товаров без g:brand
DEFAULT_QTY = 10           # в Google-фиде нет остатков -> ставим фикс. значение
CURRENCY = "UAH"
CATEGORY_ID_START = 1001   # id для создаваемых категорий
# -------------------------------------------

G = "{http://base.google.com/ns/1.0}"


def load_source():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            return f.read()
    r = requests.get(SRC, timeout=120)
    r.raise_for_status()
    return r.content


def clean_id(raw):
    """'RG 1112' -> 'RG1112' (без пробелов и спецсимволов)."""
    return re.sub(r"[^\w\-]", "", raw.strip())


def parse_price(raw):
    """'7505 UAH' -> '7505'."""
    m = re.search(r"[\d]+(?:[.,]\d+)?", raw or "")
    return m.group(0).replace(",", ".") if m else "0"


def description_html(title, text):
    """Простой текст из Google-фида -> HTML-описание (как в abertime)."""
    text = (text or "").replace("\r", "").strip()
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    html = f"<h2>{title}</h2>" + "".join(f"<p>{p}</p>" for p in paras)
    return html


def main():
    root = etree.fromstring(load_source())
    items = root.findall(".//item")

    # ---- категории из product_type ("A > B" -> родитель/потомок) ----
    cat_ids = {}          # путь -> id
    cat_list = []         # (id, name, parent_id)
    next_id = CATEGORY_ID_START

    def ensure_category(path):
        nonlocal next_id
        parts = [p.strip() for p in path.split(">") if p.strip()]
        parent = None
        key = ""
        for part in parts:
            key = f"{key}>{part}"
            if key not in cat_ids:
                cat_ids[key] = str(next_id)
                cat_list.append((str(next_id), part, parent))
                next_id += 1
            parent = cat_ids[key]
        return parent  # id самой глубокой категории

    # ---- сборка YML ----
    yml = etree.Element("yml_catalog", date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    shop = etree.SubElement(yml, "shop")
    etree.SubElement(shop, "url").text = SHOP_URL
    etree.SubElement(shop, "name").text = SHOP_NAME
    etree.SubElement(shop, "company").text = COMPANY
    if PHONE:
        etree.SubElement(shop, "phone").text = PHONE
    categories_el = etree.SubElement(shop, "categories")
    offers_el = etree.SubElement(shop, "offers")

    seen_ids = set()
    for it in items:
        def g(tag):
            return (it.findtext(G + tag) or "").strip()

        sku = g("id")
        if not sku:
            continue
        oid = clean_id(sku)
        if oid in seen_ids:           # защита от дублей id
            continue
        seen_ids.add(oid)

        in_stock = g("availability").lower().replace("_", " ") == "in stock"
        offer = etree.SubElement(
            offers_el, "offer", id=oid,
            available="true" if in_stock else "false",
            in_stock="true" if in_stock else "false",
        )
        title = g("title")
        etree.SubElement(offer, "name").text = title
        etree.SubElement(offer, "vendorCode").text = sku
        etree.SubElement(offer, "url").text = g("link")
        etree.SubElement(offer, "currencyId").text = CURRENCY
        etree.SubElement(offer, "categoryId").text = ensure_category(
            g("product_type") or "Інше")
        etree.SubElement(offer, "price").text = parse_price(g("price"))

        pics = [g("image_link")] + [
            (e.text or "").strip() for e in it.findall(G + "additional_image_link")]
        for p in pics:
            if p:
                etree.SubElement(offer, "picture").text = p

        vendor = g("brand") or DEFAULT_VENDOR
        etree.SubElement(offer, "vendor").text = vendor
        etree.SubElement(offer, "quantity_in_stock").text = (
            str(DEFAULT_QTY) if in_stock else "0")

        desc = etree.SubElement(offer, "description")
        desc.text = etree.CDATA(description_html(title, g("description")))

        # параметры (в Google-фиде их почти нет — добавляем что есть)
        param = etree.SubElement(offer, "param", name="Бренд")
        param.text = vendor
        param = etree.SubElement(offer, "param", name="Стан")
        param.text = "Новий" if g("condition") in ("", "new") else g("condition")

    # категории пишем после обхода (чтобы знать все)
    for cid, name, parent in cat_list:
        attrs = {"id": cid}
        if parent:
            attrs["parentId"] = parent
        c = etree.SubElement(categories_el, "category", **attrs)
        c.text = name

    etree.ElementTree(yml).write(
        OUT, encoding="UTF-8", xml_declaration=True, pretty_print=False)
    print(f"Готово: {len(seen_ids)} товаров -> {OUT}")


if __name__ == "__main__":
    main()
