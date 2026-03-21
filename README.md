# Cinema Alert — Barcelona (cinéfilos)

Mini aplicación en Python que consulta la cartelera de varios cines de Barcelona, compara con la última captura guardada en `data/latest_snapshot.json` y envía un resumen por **Telegram**.

## Cines (MVP)

| Cine        | Fuente principal |
|------------|-------------------|
| Verdi      | `barcelona.cines-verdi.com` (HTML) |
| Phenomena  | URL configurable (ver abajo) |
| Maldà      | API REST de WordPress |
| Zumzeig    | URL configurable (ver abajo) |
| Espai Texas| `espaitexas.cat/cartellera-cinema/` |

**Phenomena y Zumzeig** cambian de dominio o estructura con frecuencia. Si el scraper devuelve 0 películas, define la URL oficial en `.env` (`PHENOMENA_BASE_URL`, `ZUMZEIG_CARTELERA_URL`) y, si hace falta, ajusta los selectores en `src/scrapers/phenomena.py` o `zumzeig.py`.

## Requisitos

- Python 3.11+
- Bot de Telegram ([BotFather](https://t.me/BotFather)) y `chat_id` del destino (usuario o grupo)

## Configuración local

```bash
cp .env.example .env
# Rellena TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
pip install -r requirements.txt
```

### Obtener `chat_id`

Escribe algo a tu bot y abre en el navegador:

`https://api.telegram.org/bot<TU_TOKEN>/getUpdates`

Busca `"chat":{"id": ...}`.

## Ejecución

```bash
# Con Telegram (usa variables del .env)
python src/main.py
```

```bash
# Solo generar mensaje y snapshot, sin Telegram
SKIP_TELEGRAM=1 python src/main.py
```

## Tests

```bash
pytest
```

## GitHub Actions

El workflow `.github/workflows/cinema-alerts.yml` ejecuta el script los **jueves a las 08:00 UTC** (ajusta el `cron` si quieres) y hace commit de `data/latest_snapshot.json` cuando cambia.

Añade en el repositorio **Secrets**:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

El workflow necesita permiso de escritura en el contenido del repo (ya está en el YAML) para poder hacer push del snapshot.

## Primera ejecución

El archivo `data/latest_snapshot.json` incluye una fecha sentinel `1970-01-01`. La primera vez que corre el job con éxito sustituye ese snapshot por una captura real y envía un mensaje corto indicando que las siguientes ejecuciones mostrarán solo **novedades**.

## Añadir un cine

1. Crea `src/scrapers/mi_cine.py` con una clase que herede de `BaseScraper` e implemente `fetch() -> list[Film]`.
2. Registra el scraper en `src/main.py` dentro de `_run_scrapers()`.
3. Añade un test de humo o de normalización si aplica.

## Estructura

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
  scrapers/
data/
  latest_snapshot.json
  history/
tests/
```

## Notas

- No se incluyen secretos en el código: todo va por variables de entorno.
- El envío usa `parse_mode=HTML` en Telegram para evitar sorpresas con caracteres especiales.
- Respeta los `robots.txt` y no aumentes la frecuencia de peticiones más de lo necesario.
