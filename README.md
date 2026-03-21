# Cinema Alert — Barcelona (cinéfilos)

Mini aplicación en Python que consulta la cartelera de varios cines de Barcelona y envía un **resumen diario por Telegram** con **hoy, mañana y pasado mañana**. Donde la web publica sesiones con fecha (p. ej. **Verdi**), lista **horas**; el resto va en un bloque “cartelera sin horarios en este mensaje” con enlace a la web. Opcionalmente añade un bloque de **novedades** respecto al snapshot guardado en `data/latest_snapshot.json`.

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

**Opción recomendada** (si `getUpdates` en el navegador sale vacío o `@userinfobot` no responde):

```bash
export TELEGRAM_BOT_TOKEN="tu_token_de_botfather"
pip install requests   # si hace falta
python3 scripts/get_chat_id.py
```

Con el script en marcha, abre Telegram y **escribe cualquier mensaje a tu bot**. En la terminal aparecerá el número para `TELEGRAM_CHAT_ID`.

**Opción manual:** escribe a tu bot y abre `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` y busca `"chat":{"id": ...}`.

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

El workflow `.github/workflows/cinema-alerts.yml` ejecuta el script **cada día** (~07:00 hora de Madrid en invierno; el `cron` está en **UTC**: `0 6 * * *`) y hace commit de `data/latest_snapshot.json` cuando cambia. Puedes lanzarlo a mano cuando quieras: **Actions → Run workflow** (para comprobar que llega el mensaje).

Añade en el repositorio **Secrets**:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

El workflow necesita permiso de escritura en el contenido del repo (ya está en el YAML) para poder hacer push del snapshot.

## Primera ejecución

El archivo `data/latest_snapshot.json` puede incluir la fecha sentinel `1970-01-01`. La primera vez que corre con éxito guarda un snapshot real; el mensaje incluye el **resumen de 3 días** y una nota sobre el diff de novedades en ejecuciones posteriores.

Variables útiles (ver `.env.example`):

- `TIMEZONE` — por defecto `Europe/Madrid` (define qué es “hoy”).
- `APPEND_NOVELTIES` — `1` por defecto: añade al final películas nuevas respecto al snapshot anterior.

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
  digest.py
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
