# Den Hertog – OpenAI Ads productfeed

Zet de Google XML-feed van hertog.nl dagelijks om naar het OpenAI Ads-formaat (CSV) en publiceert het resultaat via GitHub Pages en/of SFTP.

## Bestanden

| Bestand | Plek in de repo | Wat het doet |
|---|---|---|
| `convert.py` | root | Haalt `https://mijn.hertog.nl/new/productfeed.xml` op en schrijft `dist/hertog_openai.csv`, `.csv.gz` en `report.txt` |
| `sftp_upload.py` | root | Uploadt de `.csv.gz` naar de OpenAI SFTP-root (alleen als secrets zijn ingesteld) |
| `feed.yml` | `.github/workflows/feed.yml` | Draait dagelijks om 05:37 UTC, en handmatig via "Run workflow" |

## Installatie

1. Maak een nieuwe (private) repo, bijv. `hertog-openai-feed`.
2. Zet `convert.py` en `sftp_upload.py` in de root en `feed.yml` in `.github/workflows/`.
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions → "OpenAI Ads feed – Den Hertog" → **Run workflow**.
5. Feed-URL na de eerste run: `https://<github-gebruiker>.github.io/hertog-openai-feed/hertog_openai.csv`
   Die URL gebruik je in Ads Manager → Feeds → "Connect your feed via URL".

Let op: een GitHub Pages-site van een private repo is publiek bereikbaar (op betaalde plannen), tenzij je toegangsbeheer aanzet. De feed bevat alleen publieke productdata, dus dat is meestal geen probleem.

### Optioneel: SFTP in plaats van (of naast) URL

Als Ads Manager SFTP-gegevens geeft, zet ze in Settings → Secrets and variables → Actions:

- `OPENAI_SFTP_HOST`
- `OPENAI_SFTP_USER`
- `OPENAI_SFTP_PASSWORD`
- `OPENAI_SFTP_PORT` (optioneel, standaard 22)

De workflow uploadt dan elke dag `hertog_openai.csv.gz` naar de root.

## Wat de converter doet

- Mapt de `g:`-velden naar OpenAI-veldnamen (`item_id`, `title`, `url`, `image_url`, `price`, enz.).
- Vult `brand` met "Den Hertog" zolang de XML geen `g:brand` heeft. Komt er later een `g:brand` (bijv. uitgever) in de feed, dan wordt die automatisch gebruikt.
- Vult `seller_name` en `seller_url`.
- Zet `is_ads_eligible=true` voor in_stock / pre_order / backorder, `false` voor out_of_stock.
- Laat ongeldige GTIN's weg, maakt van "-" bij categorie een leeg veld, kort titels in tot 150 tekens.
- Slaat rijen over zonder id, titel, URL, afbeelding of geldige prijs.
- **Veiligheidsrem:** bij minder dan 1.000 eligible producten wordt niets gepubliceerd, zodat een kapotte bronfeed de live feed niet leegmaakt.

## Instellingen (environment variables)

| Variabele | Standaard | Betekenis |
|---|---|---|
| `BRAND_FALLBACK` | `Den Hertog` | Merk als de XML er geen heeft |
| `KEEP_OUT_OF_STOCK` | `true` | `false` = uitverkochte producten helemaal weglaten |
| `MIN_PRODUCTS` | `1000` | Minimum aantal eligible producten om te publiceren |

## Controle

Na elke run staat het rapport in de samenvatting van de Actions-run en op `.../report.txt`: aantallen, overgeslagen rijen en meldingen zoals kapotte apostrofs in URL's ("Jessica39s").
