"""kolenke agent: runs kolenke on this computer and connects it to your cloud panel.

    .venv/bin/python agent.py pair https://panel.example.kz CODE   — once: link this computer to your account
    .venv/bin/python agent.py                                        — run: local site + connection to the panel
    .venv/bin/python agent.py unpair                                  — forget the panel on this computer

Everything that touches hh.kz, Gmail and your data runs here, so hh sees this network's IP.
The panel only forwards requests; it never gets your hh session, passwords or vacancies database.
"""
import asyncio
import base64
import json
import os
import platform
import sys
from urllib.parse import urlparse

import httpx

import agent_link

PORT = int(os.environ.get("KOLENKE_PORT", "8765"))
LOCAL = f"http://127.0.0.1:{PORT}"
ALLOWED = ("/api/",)  # the panel may reach the kolenke API and nothing else on this computer


def pair(server: str, code: str):
    server = server.rstrip("/")
    if urlparse(server).scheme not in ("http", "https"):
        sys.exit("Адрес панели должен начинаться с https:// (или http:// для локальной проверки)")
    if urlparse(server).scheme == "http" and urlparse(server).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("Для внешнего сервера нужен https://, иначе токен агента можно перехватить")
    r = httpx.post(f"{server}/agent/pair", json={"code": code, "name": platform.node() or "компьютер"}, timeout=20)
    if r.status_code != 200:
        sys.exit("Не получилось: " + (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text))
    data = r.json()
    agent_link.save_config({"server": server, "token": data["token"], "email": data["email"]})
    print(f"Готово: этот компьютер привязан к {data['email']}. Запускайте: .venv/bin/python agent.py")


async def handle(app, msg) -> dict:
    """Runs one request from the panel through the local kolenke app (with all its own checks)."""
    path = msg.get("path") or ""
    if not path.startswith(ALLOWED) or ".." in path:
        return {"status": 403, "headers": {"content-type": "application/json"},
                "body": base64.b64encode(b'{"detail":"forbidden"}').decode()}
    headers = {k: v for k, v in (msg.get("headers") or {}).items() if k.lower() in ("content-type", "x-jobbot")}
    headers["host"] = f"127.0.0.1:{PORT}"  # the local app only answers to localhost
    url = path + (("?" + msg["query"]) if msg.get("query") else "")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=LOCAL, timeout=85) as client:
        r = await client.request(msg.get("method", "GET"), url, headers=headers, content=base64.b64decode(msg.get("body") or ""))
    keep = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "content-disposition")}
    return {"status": r.status_code, "headers": keep, "body": base64.b64encode(r.content).decode()}


async def relay_loop(app, cfg):
    import websockets

    url = cfg["server"].replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/agent/ws"
    delay = 2
    while True:
        try:
            async with websockets.connect(url, additional_headers={"Authorization": "Bearer " + cfg["token"]},
                                          ping_interval=25, max_size=40 * 1024 * 1024) as ws:
                agent_link.set_state(connected=True, error=None)
                print(f"Панель: подключено к {cfg['server']} как {cfg['email']}")
                delay = 2
                await ws.send(json.dumps({"type": "hello", "version": 1}))

                async def answer(msg):
                    try:
                        res = await handle(app, msg)
                    except Exception as e:  # one broken request must not drop the connection
                        res = {"status": 500, "headers": {"content-type": "application/json"},
                               "body": base64.b64encode(json.dumps({"detail": str(e)[:200]}).encode()).decode()}
                    await ws.send(json.dumps({"type": "res", "id": msg["id"], **res}))

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "req":
                        asyncio.create_task(answer(msg))
        except websockets.exceptions.InvalidStatus as e:
            agent_link.set_state(connected=False, error=f"панель ответила {e.response.status_code}")
        except websockets.exceptions.ConnectionClosed as e:
            agent_link.set_state(connected=False, error=None)
            if e.rcvd and e.rcvd.code == 4401:
                agent_link.set_state(error="панель отозвала доступ этого компьютера — привяжите его заново")
                print("Панель отозвала доступ этого компьютера. Привяжите заново: agent.py pair …")
                return
        except OSError as e:
            agent_link.set_state(connected=False, error=f"нет связи с панелью: {e.strerror or e}")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


async def run():
    import uvicorn
    import app as kolenke  # the usual local kolenke: database, autopilot, hh bot

    cfg = agent_link.load_config()
    server = uvicorn.Server(uvicorn.Config(kolenke.app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False))
    tasks = [server.serve()]
    if cfg:
        agent_link.set_state(server=cfg["server"], email=cfg["email"])
        tasks.append(relay_loop(kolenke.app, cfg))
    else:
        print("Панель не привязана: работает только локально. Привязать: .venv/bin/python agent.py pair <адрес> <код>")
    print(f"kolenke: {LOCAL}")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["pair"] and len(args) == 3:
        pair(args[1], args[2])
    elif args[:1] == ["unpair"]:
        agent_link.forget()
        print("Привязка к панели удалена с этого компьютера")
    elif not args:
        asyncio.run(run())
    else:
        print(__doc__)
