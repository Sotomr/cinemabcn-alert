# Cinema Alert — Barcelona

Aplicació en **Python 3.11+** que consulta la **cartellera** de diversos cinemes de Barcelona, enriqueix els títols amb **notes TMDb / enllaç IMDb** (opcional) i envia un **resum per Telegram** en **català**.

La finestra temporal per defecte és **avui i demà** (zona `Europe/Madrid`). El digest principal (mode Telegram recomanat) es divideix en **dos missatges**:

1. **Top global** — les millors pel·lícules per nota (fins a `DIGEST_GLOBAL_TOP`, per defecte 10), agrupades per títol, amb la llista de cinemes on es projecten.
2. **Horaris** — les mateixes pel·lícules amb **sessions detallades** per cinema i dia.

Opcionalment s’afegeix un bloc de **novetats** (altes respecte a `data/latest_snapshot.json`).

## Cinemes

| Cinema | Font / tècnica |
|--------|----------------|
| **Filmoteca de Catalunya** | Agenda setmanal (`filmoteca.cat`, HTML) |
| **Phenomena** | `phenomena-experience.com` (configurable) |
| **Verdi** | Llistat + pàgines de pel·lícula (`cines-verdi.com`) |
| **Mooby Balmes** | JSON embegut `window.shops` a `moobycinemas.com/balmes` |
| **Maldà** | WordPress, pàgines per pel·lícula |
| **Zumzeig** | Calendari mensual (configurable) |
| **Cinemes Girona** | Cartellera Admit One (`cinemesgirona.cat`) |
| **Renoir Floridablanca** | Web Renoir / Pillalas |
| **Espai Texas** | `espaitexas.cat` |

**Phenomena** i **Zumzeig** canvien sovint d’URL o d’estructura. Si un scraper retorna 0 títols, defineix la URL a `.env` (`PHENOMENA_BASE_URL`, `ZUMZEIG_CARTELERA_URL`) i revisa el mòdul corresponent a `src/scrapers/`.

**Mooby Balmes** no necessita API: tota la cartellera ve en un objecte JSON dins del HTML (`window.shops`). Opcional: `MOOBY_BALMES_URL`.

## Requisits

- Python 3.11+
- Bot de Telegram ([BotFather](https://t.me/BotFather)) i `chat_id` del destí (usuari o grup)
- (Opcional) clau **TMDb** per notes i enllaç IMDb — [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)

## Configuració local

```bash
cp .env.example .env
# Omple TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID (i opcionalment TMDB_API_KEY)
pip install -r requirements.txt
```

### Obtenir el `chat_id`

**Recomanat** (si `getUpdates` buit o `@userinfobot` no respon):

```bash
export TELEGRAM_BOT_TOKEN="el_teu_token_de_botfather"
pip install requests   # si cal
python3 scripts/get_chat_id.py
```

Amb el script en marxa, escriu qualsevol missatge al bot a Telegram; a la terminal sortirà el número per a `TELEGRAM_CHAT_ID`.

**Manual:** escriu al bot i obre `https://api.telegram.org/bot<TOKEN>/getUpdates` i busca `"chat":{"id": ...}`.

## Execució

```bash
python src/main.py
```

```bash
# Només generar missatge i snapshot, sense Telegram
SKIP_TELEGRAM=1 python src/main.py
```

## Tests

```bash
pytest
```

## GitHub Actions

El workflow `.github/workflows/cinema-alerts.yml` executa el script **cada dia** cap a les **10:00–11:00** (hora Barcelona segons estació; el `cron` és en **UTC**: `0 9 * * *`). Pots llançar-lo manualment: **Actions → Run workflow**.

**Secrets** del repositori:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TMDB_API_KEY` (opcional; sense clau, el digest funciona però sense notes TMDb)

El workflow necessita permís d’escriptura al contingut del repo per fer push del snapshot quan canvia.

## Primera execució

`data/latest_snapshot.json` pot portar una data sentinella (`1970-01-01`). La primera passada amb èxit desa un snapshot real; el missatge inclou una nota que les **novetats** tindran sentit a partir de la següent execució.

## Variables d’entorn (resum)

Vegeu `.env.example` per la llista completa. Les més rellevants:

| Variable | Per defecte | Descripció |
|----------|---------------|------------|
| `TIMEZONE` | `Europe/Madrid` | Defineix «avui» i «demà». |
| `APPEND_NOVELTIES` | `1` | Afegeix novetats respecte al snapshot anterior. |
| `TMDB_API_KEY` | — | Notes + enllaç IMDb; caché a `data/tmdb_cache_v*.json`. |
| `TMDB_MAX_FILMS` | `200` | Màxim de títols a enriqueir per execució (prioritat sessions avui/demà). |
| `TMDB_MIN_VOTES` | `1` | Vots mínims a TMDb per mostrar nota. |
| `DIGEST_GLOBAL_TOP` | `10` | Mida del top global (i del segon missatge d’horaris). |
| `DIGEST_TELEGRAM_BY_CINEMA` | `1` | `1` = format 2 missatges (top + horaris). `0` = digest per seccions en un o més blocs (`build_digest_sections`). |
| `DIGEST_ONLY_TODAY` | `0` | `1` = només avui (útil per proves); per defecte avui + demà. |
| `DIGEST_TOP_PER_CINEMA` | `3` | Afecta el mode seccions (`DIGEST_TELEGRAM_BY_CINEMA=0`), no el top global. |
| `DIGEST_EXTRA_UNRATED` | `0` | Pel·lícules sense nota addicionals al mode per cinema. |
| `DIGEST_MAX_VERDI_PER_DAY` | `0` | `0` = sense límit; retalla llistats Verdi al mode per seccions. |
| `PHENOMENA_BASE_URL` | — | URL alternativa Phenomena. |
| `ZUMZEIG_CARTELERA_URL` | — | URL alternativa Zumzeig (calendari). |
| `MOOBY_BALMES_URL` | — | URL cartellera Mooby Balmes. |
| `SKIP_TELEGRAM` / `DRY_RUN` | — | Execució sense enviar a Telegram. |
| `DEBUG_FOOTER` | `0` | Peu amb indicacions de depuració. |

Els missatges es parteixen automàticament si superen el límit de Telegram (~4096 caràcters), sense tallar a mitja línia quan és possible.

## Afegir un cinema

1. Crea `src/scrapers/el_teu_cine.py` amb una classe que hereti de `BaseScraper` i implementi `fetch() -> list[Film]`.
2. Registra el scraper a `src/main.py` dins `_run_scrapers()`.
3. Afegeix tests (parseig o humo) si escau.

Cada `Film` ha de tenir `cinema`, `title`, `url`, `source_section` i, si la web ho permet, `shows` amb `datetime` en format `YYYYMMDD HH:MM`.

## Estructura del projecte

```text
src/
  main.py
  config.py
  models.py
  notifier.py
  diff_engine.py
  classifiers.py
  storage.py
  utils.py
  digest.py
  tmdb_ratings.py
  scrapers/
    base.py
    filmoteca.py
    phenomena.py
    verdi.py
    mooby_balmes.py
    malda.py
    zumzeig.py
    girona.py
    renoir.py
    espai_texas.py
data/
  latest_snapshot.json
  history/
tests/
.github/workflows/
```

## Notes

- No s’inclouen secrets al codi: tot per variables d’entorn.
- L’enviament usa `parse_mode=HTML` a Telegram.
- Respecta `robots.txt` i no sobrecarreguis les webs amb massa peticions.
