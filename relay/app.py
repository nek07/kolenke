"""kolenke cloud panel: accounts, invites and a secure relay to each user's own agent.

The panel stores no vacancies, resumes, hh sessions or passwords. A browser (phone, laptop) talks to the panel;
the panel forwards /api/* over a WebSocket to the agent running on the user's computer, so hh.kz sees the IP
of the network where the agent runs.

Run:  uvicorn relay.app:app --host 0.0.0.0 --port 8080        (behind HTTPS in production)
Invite yourself (first account = owner) or a friend:  python -m relay.manage invite
"""
import asyncio
import base64
import json
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from relay import store

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "static" / "index.html"          # the same kolenke interface the agent serves locally
PAGES = Path(__file__).resolve().parent / "static"
COOKIE = "kolenke_session"
SECURE_COOKIES = os.environ.get("RELAY_SECURE_COOKIES", "0") == "1"  # set to 1 behind HTTPS
MAX_BODY = 15 * 1024 * 1024
TIMEOUT = 90  # seconds to wait for the agent's answer
FORWARD_REQ = ("content-type", "x-jobbot")
FORWARD_RES = ("content-type", "content-disposition")

store.init()
app = FastAPI(title="kolenke panel", docs_url=None, redoc_url=None, openapi_url=None)


# ---------- connected agents ----------
class AgentConn:
    def __init__(self, ws: WebSocket, agent: dict):
        self.ws, self.agent, self.pending = ws, agent, {}
        self.connected_at = store.now()


AGENTS: dict[int, AgentConn] = {}  # user_id -> live connection (one per user; a new one replaces the old)


async def call_agent(user_id: int, envelope: dict) -> dict:
    conn = AGENTS.get(user_id)
    if not conn:
        raise LookupError
    rid = secrets.token_hex(8)
    fut = asyncio.get_running_loop().create_future()
    conn.pending[rid] = fut
    try:
        await conn.ws.send_text(json.dumps({"type": "req", "id": rid, **envelope}))
        return await asyncio.wait_for(fut, TIMEOUT)
    finally:
        conn.pending.pop(rid, None)


# ---------- small protections ----------
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(key: str, limit: int, per: int = 60):
    now, q = time.monotonic(), _hits[key]
    while q and now - q[0] > per:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Слишком много попыток. Подождите минуту")
    q.append(now)


TRUST_PROXY = os.environ.get("RELAY_TRUST_PROXY", "0") == "1"  # set to 1 only behind your own reverse proxy


def client_ip(request: Request) -> str:
    direct = request.client.host if request.client else ""
    if TRUST_PROXY:  # the proxy writes the real address; without a proxy anyone could forge this header
        return (request.headers.get("x-forwarded-for") or direct).split(",")[0].strip()
    return direct


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith(("/api/", "/relay/", "/auth/")):
        # custom header = no cross-site form/fetch can send it without a CORS preflight, which we never allow
        if request.headers.get("x-jobbot") != "1":
            return JSONResponse({"detail": "Запрос отклонён"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def current_user(request: Request):
    return store.session_user(request.cookies.get(COOKIE))


def need_user(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Войдите в аккаунт")
    return u


def set_session(resp: Response, user_id: int):
    resp.set_cookie(COOKIE, store.new_session(user_id), max_age=store.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=SECURE_COOKIES, path="/")


# ---------- pages ----------
@app.get("/")
def home(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", 303)
    if not store.agents_of(u["id"]):
        return RedirectResponse("/connect", 303)
    # the same page as on the agent, marked so it knows to show panel things (account, «агент не в сети»)
    page = UI.read_text().replace("<head>", '<head>\n<meta name="kolenke-panel" content="1">', 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/login")
@app.get("/register")
def auth_page():
    return FileResponse(PAGES / "auth.html")


@app.get("/connect")
def connect_page(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", 303)
    return FileResponse(PAGES / "connect.html")


# ---------- accounts ----------
@app.post("/auth/register")
async def register(request: Request):
    rate_limit("reg:" + client_ip(request), 5)
    data = await request.json()
    try:
        uid = store.register(data.get("email"), data.get("password"), data.get("invite"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"ok": True})
    set_session(resp, uid)
    return resp


@app.post("/auth/login")
async def login(request: Request):
    rate_limit("login:" + client_ip(request), 8)
    data = await request.json()
    u = store.authenticate(data.get("email"), data.get("password"))
    if not u:
        raise HTTPException(400, "Неверный email или пароль")
    resp = JSONResponse({"ok": True})
    set_session(resp, u["id"])
    return resp


@app.post("/auth/logout")
def logout(request: Request):
    store.end_session(request.cookies.get(COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/relay/me")
def me(request: Request):
    u = need_user(request)
    conn = AGENTS.get(u["id"])
    return {
        "email": u["email"], "is_admin": bool(u["is_admin"]),
        "online": bool(conn), "agent": conn.agent["name"] if conn else None, "since": conn.connected_at if conn else None,
        "agents": store.agents_of(u["id"]),
    }


@app.post("/relay/pair-code")
def pair_code(request: Request):
    u = need_user(request)
    return {"code": store.new_pair_code(u["id"]), "minutes": store.PAIR_MINUTES, "server": str(request.base_url).rstrip("/")}


@app.post("/relay/agents/{agent_id}/delete")
async def delete_agent(agent_id: int, request: Request):
    u = need_user(request)
    if not store.remove_agent(u["id"], agent_id):
        raise HTTPException(404)
    conn = AGENTS.get(u["id"])
    if conn and conn.agent["id"] == agent_id:
        await conn.ws.close(code=4401)
    return {"ok": True}


@app.post("/relay/invites")
def invite(request: Request):
    u = need_user(request)
    if not u["is_admin"]:
        raise HTTPException(403, "Приглашения создаёт владелец панели")
    return {"code": store.new_invite()}


# ---------- agent side ----------
@app.post("/agent/pair")
async def agent_pair(request: Request):
    rate_limit("pair:" + client_ip(request), 10)
    data = await request.json()
    try:
        token, user = store.pair(data.get("code"), data.get("name"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"token": token, "email": user["email"]}


@app.websocket("/agent/ws")
async def agent_ws(ws: WebSocket):
    token = (ws.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    agent = store.agent_by_token(token)
    if not agent:
        await ws.close(code=4401)  # the agent stops retrying on this code
        return
    await ws.accept()
    uid = agent["user_id"]
    old = AGENTS.get(uid)
    conn = AGENTS[uid] = AgentConn(ws, agent)
    if old:
        await old.ws.close(code=4000)
    store.touch_agent(agent["id"])
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "res" and msg.get("id") in conn.pending:
                fut = conn.pending[msg["id"]]
                if not fut.done():
                    fut.set_result(msg)
            elif msg.get("type") == "hello":
                store.touch_agent(agent["id"])
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
        pass
    finally:
        if AGENTS.get(uid) is conn:
            del AGENTS[uid]
        for fut in conn.pending.values():
            if not fut.done():
                fut.set_exception(LookupError())
        store.touch_agent(agent["id"])


# ---------- relay of the kolenke API ----------
@app.api_route("/api/{path:path}", methods=["GET", "POST", "DELETE", "PUT"])
async def relay_api(path: str, request: Request):
    u = need_user(request)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "Файл слишком большой")
    envelope = {
        "method": request.method, "path": "/api/" + path, "query": request.url.query,
        "headers": {k: v for k, v in request.headers.items() if k.lower() in FORWARD_REQ},
        "body": base64.b64encode(body).decode(),
    }
    try:
        res = await call_agent(u["id"], envelope)
    except (LookupError, asyncio.TimeoutError):
        return JSONResponse({"detail": "Компьютер с агентом kolenke не в сети", "code": "agent_offline"}, status_code=503)
    headers = {k: v for k, v in (res.get("headers") or {}).items() if k.lower() in FORWARD_RES}
    return Response(base64.b64decode(res.get("body") or ""), status_code=int(res.get("status", 502)), headers=headers)
