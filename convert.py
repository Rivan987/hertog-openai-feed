#!/usr/bin/env python3
"""
Den Hertog – Google XML (Atom) productfeed -> OpenAI Ads productfeed (CSV / CSV.GZ)

Bron:   https://mijn.hertog.nl/new/productfeed.xml
Output: dist/hertog_openai.csv      (voor "Connect your feed via URL")
        dist/hertog_openai.csv.gz   (voor SFTP-upload)
        dist/report.txt             (controlerapport)

Alleen standaardbibliotheek, geen extra packages nodig.
"""

import csv
import gzip
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

FEED_URL = os.environ.get("FEED_URL", "https://mijn.hertog.nl/new/productfeed.xml")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
OUT_NAME = os.environ.get("OUT_NAME", "hertog_openai")

SELLER_NAME = os.environ.get("SELLER_NAME", "Den Hertog")
SELLER_URL = os.environ.get("SELLER_URL", "https://www.hertog.nl")
# Gebruikt zolang de XML geen g:brand (bijv. uitgever) bevat.
BRAND_FALLBACK = os.environ.get("BRAND_FALLBACK", "Den Hertog")
# true  = uitverkochte producten wel in de feed, maar is_ads_eligible=false
# false = uitverkochte producten helemaal weglaten
KEEP_OUT_OF_STOCK = os.environ.get("KEEP_OUT_OF_STOCK", "true").lower() == "true"
MIN_PRODUCTS = int(os.environ.get("MIN_PRODUCTS", "1000"))

NS_G = "http://base.google.com/ns/1.0"
NS_ATOM = "http://www.w3.org/2005/Atom"
G = "{%s}" % NS_G

COLUMNS = [
    "item_id", "title", "description", "url", "brand", "seller_name",
    "image_url", "availability", "price", "gtin", "condition",
    "product_category", "seller_url", "is_ads_eligible",
]

VALID_AVAILABILITY = {"in_stock", "out_of_stock", "pre_order", "backorder", "unknown"}
AVAILABILITY_MAP = {"preorder": "pre_order", "in stock": "in_stock", "out of stock": "out_of_stock"}
VALID_CONDITION = {"new", "refurbished", "used"}
PLACEHOLDERS = {"", "-", "null", "none", "n/a", "na", "unknown", "0"}
PRICE_RE = re.compile(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*([A-Za-z]{3})\s*$")
WS_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    if not value:
        return ""
    value = TAG_RE.sub(" ", value)          # eventuele HTML eruit
    value = WS_RE.sub(" ", value).strip()   # dubbele spaties / regeleinden
    return value


def is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDERS


def valid_gtin(code: str) -> bool:
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def normalize_price(raw: str):
    m = PRICE_RE.match(raw or "")
    if not m:
        return None
    amount = float(m.group(1).replace(",", "."))
    if amount <= 0:
        return None
    return f"{amount:.2f} {m.group(2).upper()}"


def gtext(entry, name: str) -> str:
    el = entry.find(G + name)
    return el.text.strip() if el is not None and el.text else ""


def download(url: str) -> str:
    path = os.path.join(OUT_DIR, "source.xml")
    req = urllib.request.Request(url, headers={"User-Agent": "hertog-openai-feed/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(path, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    return path


def convert(source_path: str):
    stats = Counter()
    issues = Counter()
    examples = {}
    seen_ids = set()
    rows = []

    def note(kind, item_id):
        issues[kind] += 1
        examples.setdefault(kind, []).append(item_id) if len(examples.get(kind, [])) < 5 else None

    for _, el in ET.iterparse(source_path, events=("end",)):
        if el.tag not in (f"{{{NS_ATOM}}}entry", "entry", "item"):
            continue
        stats["entries"] += 1

        item_id = gtext(el, "id")
        title = clean_text(gtext(el, "title"))
        description = clean_text(gtext(el, "description"))
        url = gtext(el, "link")
        image_url = gtext(el, "image_link")
        availability = gtext(el, "availability").lower()
        availability = AVAILABILITY_MAP.get(availability, availability)
        price = normalize_price(gtext(el, "price"))
        gtin = gtext(el, "gtin")
        condition = gtext(el, "condition").lower()
        brand = clean_text(gtext(el, "brand"))
        category = clean_text(gtext(el, "google_product_category") or gtext(el, "product_type"))
        el.clear()

        # --- verplichte velden; rij overslaan als iets ontbreekt
        if not item_id:
            note("geen id (overgeslagen)", "?")
            continue
        if item_id in seen_ids:
            note("dubbel id (overgeslagen)", item_id)
            continue
        if not title:
            note("geen titel (overgeslagen)", item_id)
            continue
        if not url.startswith("http"):
            note("geen/ongeldige url (overgeslagen)", item_id)
            continue
        if not image_url.startswith("http"):
            note("geen afbeelding (overgeslagen)", item_id)
            continue
        if price is None:
            note("ongeldige prijs (overgeslagen)", item_id)
            continue
        if availability not in VALID_AVAILABILITY:
            note("onbekende availability -> unknown", item_id)
            availability = "unknown"

        # --- opschonen / aanvullen
        if not description:
            description = title
        if description == title:
            issues["description gelijk aan titel"] += 1
        if not brand or is_placeholder(brand):
            brand = BRAND_FALLBACK
            issues["brand = fallback"] += 1
        if gtin and not valid_gtin(gtin):
            note("ongeldige gtin (weggelaten)", item_id)
            gtin = ""
        if condition not in VALID_CONDITION:
            condition = "new"
        if is_placeholder(category):
            category = ""
        if "39" in url and re.search(r"[a-zA-Z]39[a-zA-Z]", url):
            note("verdachte '39' in url (kapotte apostrof?)", item_id)
        if image_url.startswith("http://"):
            image_url = "https://" + image_url[len("http://"):]
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]

        eligible = availability in ("in_stock", "pre_order", "backorder")
        if not eligible and not KEEP_OUT_OF_STOCK:
            stats["uitverkocht weggelaten"] += 1
            continue

        seen_ids.add(item_id)
        stats["ads_eligible" if eligible else "niet_eligible"] += 1
        rows.append({
            "item_id": item_id,
            "title": title[:150],
            "description": description[:5000],
            "url": url,
            "brand": brand[:70],
            "seller_name": SELLER_NAME,
            "image_url": image_url,
            "availability": availability,
            "price": price,
            "gtin": gtin,
            "condition": condition,
            "product_category": category,
            "seller_url": SELLER_URL,
            "is_ads_eligible": "true" if eligible else "false",
        })

    return rows, stats, issues, examples


def write_outputs(rows):
    csv_path = os.path.join(OUT_DIR, f"{OUT_NAME}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)
    with open(csv_path, "rb") as src, gzip.open(csv_path + ".gz", "wb") as dst:
        dst.write(src.read())
    return csv_path


def write_report(rows, stats, issues, examples):
    lines = [
        "Den Hertog -> OpenAI Ads feed",
        f"Bron: {FEED_URL}",
        "",
        f"Entries in XML:          {stats['entries']}",
        f"Rijen in output:         {len(rows)}",
        f"  is_ads_eligible=true:  {stats['ads_eligible']}",
        f"  is_ads_eligible=false: {stats['niet_eligible']}",
        f"Uitverkocht weggelaten:  {stats['uitverkocht weggelaten']}",
        "",
        "Meldingen:",
    ]
    for kind, n in issues.most_common():
        ex = ", ".join(examples.get(kind, []))
        lines.append(f"  {kind}: {n}" + (f"  (bijv. {ex})" if ex else ""))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(OUT_DIR, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    source = sys.argv[1] if len(sys.argv) > 1 else download(FEED_URL)
    rows, stats, issues, examples = convert(source)
    write_report(rows, stats, issues, examples)
    if stats["ads_eligible"] < MIN_PRODUCTS:
        # Niet publiceren: voorkomt dat een kapotte bronfeed de live feed leegmaakt.
        sys.exit(f"FOUT: slechts {stats['ads_eligible']} eligible producten (minimum {MIN_PRODUCTS}). Output niet gepubliceerd.")
    write_outputs(rows)
    if source.endswith("source.xml"):
        os.remove(source)


if __name__ == "__main__":
    main()
