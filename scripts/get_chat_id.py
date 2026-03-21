#!/usr/bin/env python3
"""
Obtiene tu TELEGRAM_CHAT_ID escribiendo a TU bot (no hace falta userinfobot).

Uso:
  cd /Users/ferransoto/cinema-alert
  export TELEGRAM_BOT_TOKEN="tu_token_de_botfather"
  python3 scripts/get_chat_id.py

Luego abre Telegram, escribe cualquier cosa a @cinemabcn_alert_bot (o tu bot).
En unos segundos verás el chat_id aquí.
"""

from __future__ import annotations

import os
import sys
import time

try:
    import requests
except ImportError:
    print("Instala requests: pip install requests")
    sys.exit(1)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Define TELEGRAM_BOT_TOKEN con el token de BotFather, ejemplo:")
        print('  export TELEGRAM_BOT_TOKEN="123456:ABC..."')
        sys.exit(1)

    base = f"https://api.telegram.org/bot{token}"
    print("Esperando un mensaje a tu bot…")
    print("→ Abre Telegram y escribe algo a TU bot (el que creaste con BotFather).")
    print("   (Este script no contesta en Telegram; solo lee aquí el número.)\n")

    # Borra webhook por si bloqueaba getUpdates
    try:
        requests.get(f"{base}/deleteWebhook", timeout=10)
    except Exception:
        pass

    for _ in range(12):  # hasta ~10 min (long poll 50s por vuelta)
        try:
            r = requests.get(
                f"{base}/getUpdates",
                params={"timeout": 50},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                print("Error API:", data)
                break
            for u in data.get("result") or []:
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue
                chat = msg.get("chat") or {}
                cid = chat.get("id")
                typ = chat.get("type")
                if cid is not None:
                    print("\n✅ Tu TELEGRAM_CHAT_ID es:\n")
                    print(f"   {cid}")
                    print("\nCópialo en GitHub → Settings → Secrets → TELEGRAM_CHAT_ID\n")
                    return
        except requests.RequestException as e:
            print("Error de red:", e)
            time.sleep(2)
        time.sleep(1)

    print("\nNo llegó ningún mensaje. Prueba:")
    print("  - Escribir al bot correcto (el de este token).")
    print("  - Probar desde el móvil con datos en vez de WiFi.")
    sys.exit(1)


if __name__ == "__main__":
    main()
