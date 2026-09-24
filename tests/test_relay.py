"""Cloud panel: invites, accounts, protection, pairing, relay to the agent, isolation between users,
and an end-to-end run of a real panel server with a real agent process."""
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import ROOT
from relay import app as relay_app
from relay import store


@pytest.fixture(autouse=True)
def clean_relay():
    for t in ("users", "invites", "sessions", "pair_codes", "agents"):
        store.x(f"DELETE FROM {t}")
    relay_app._hits.clear()
    relay_app.AGENTS.clear()


def panel():
    c = TestClient(relay_app.app, base_url="http://panel.test")
    c.headers.update({"X-JobBot": "1"})
    return c


def signup(c, email="me@x.kz", password="password1"):
    code = store.new_invite()
    r = c.post("/auth/register", json={"email": email, "password": password, "invite": code})
    assert r.status_code == 200, r.text
    return c


# ---------- accounts ----------
def test_even_the_first_account_needs_an_invite():
    c = panel()
    r = c.post("/auth/register", json={"email": "me@x.kz", "password": "password1", "invite": ""})
    assert r.status_code == 400 and "Приглашение" in r.json()["detail"]


def test_first_account_is_owner_and_invites_are_single_use():
    signup(panel(), "owner@x.kz")
    code = store.new_invite()
    assert panel().post("/auth/register", json={"email": "a@x.kz", "password": "password1", "invite": code}).status_code == 200
    assert panel().post("/auth/register", json={"email": "b@x.kz", "password": "password1", "invite": code}).status_code == 400
    admins = {u["email"]: u["is_admin"] for u in store.q("SELECT email, is_admin FROM users")}
    assert admins == {"owner@x.kz": 1, "a@x.kz": 0}


def test_only_the_owner_makes_invites():
    owner = signup(panel(), "owner@x.kz")
    friend = signup(panel(), "friend@x.kz")
    assert owner.post("/relay/invites").status_code == 200
    assert friend.post("/relay/invites").status_code == 403


def test_login_logout_and_passwords_are_hashed():
    signup(panel(), "me@x.kz", "correct horse")
    assert "correct horse" not in json.dumps(store.q("SELECT * FROM users"))
    c = panel()
    assert c.post("/auth/login", json={"email": "me@x.kz", "password": "wrong pass"}).status_code == 400
    assert c.post("/auth/login", json={"email": "ME@x.kz", "password": "correct horse"}).status_code == 200
    assert c.get("/relay/me").json()["email"] == "me@x.kz"
    c.post("/auth/logout")
    assert c.get("/relay/me").status_code == 401


def test_login_attempts_are_limited():
    c = panel()
    codes = [c.post("/auth/login", json={"email": "x@x.kz", "password": "nope-nope"}).status_code for _ in range(10)]
    assert codes[:8] == [400] * 8 and codes[-1] == 429


def test_forged_forwarded_for_does_not_bypass_the_limit():
    c = panel()
    codes = [c.post("/auth/login", json={"email": "x@x.kz", "password": "nope-nope"}, headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(10)]
    assert codes[-1] == 429


def test_state_changes_need_the_jobbot_header():
    c = signup(panel())
    assert c.post("/relay/pair-code", headers={"X-JobBot": ""}).status_code == 403
    assert c.post("/auth/logout", headers={"X-JobBot": ""}).status_code == 403


def test_pages_route_by_state():
    c = TestClient(relay_app.app, base_url="http://panel.test", follow_redirects=False)
    assert c.get("/").headers["location"] == "/login"
    c.headers.update({"X-JobBot": "1"})
    signup(c)
    assert c.get("/").headers["location"] == "/connect"
    store.pair(store.new_pair_code(store.q("SELECT id FROM users")[0]["id"]), "Mac")
    page = c.get("/")
    assert page.status_code == 200 and 'name="kolenke-panel"' in page.text


# ---------- pairing & relay ----------
def paired_token(c):
    code = c.post("/relay/pair-code").json()["code"]
    r = c.post("/agent/pair", json={"code": code, "name": "Mac Абылая"})
    assert r.status_code == 200
    assert c.post("/agent/pair", json={"code": code, "name": "again"}).status_code == 400  # one-time code
    return r.json()["token"]


def test_api_needs_login_and_an_online_agent():
    assert panel().get("/api/status").status_code == 401
    c = signup(panel())
    r = c.get("/api/status")
    assert r.status_code == 503 and r.json()["code"] == "agent_offline"


def test_bad_agent_token_is_refused():
    with pytest.raises(WebSocketDisconnect) as e:
        with panel().websocket_connect("/agent/ws", headers={"authorization": "Bearer nope"}) as ws:
            ws.receive_text()
    assert e.value.code == 4401


def relay_once(c, ws, method, path, answer, **kw):
    """Browser request in a thread, fake agent answers in this thread."""
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", c.request(method, path, **kw)))
    t.start()
    msg = json.loads(ws.receive_text())
    ws.send_text(json.dumps({"type": "res", "id": msg["id"], **answer}))
    t.join(5)
    return msg, out["r"]


def test_relay_roundtrip_passes_only_safe_headers():
    # «with» keeps one event loop for the browser request and the agent socket, like a real server
    # (without it TestClient gives every request its own loop and the answer never meets the waiting request)
    with signup(panel()) as c, c.websocket_connect("/agent/ws", headers={"authorization": "Bearer " + paired_token(c)}) as ws:
        assert c.get("/relay/me").json()["online"] is True
        answer = {"status": 200, "headers": {"content-type": "application/json", "set-cookie": "evil=1"},
                  "body": base64.b64encode(b'{"running": false}').decode()}
        msg, r = relay_once(c, ws, "POST", "/api/settings?x=1", answer, json={"full_name": "Аня"})
    assert msg["path"] == "/api/settings" and msg["query"] == "x=1" and msg["method"] == "POST"
    assert json.loads(base64.b64decode(msg["body"])) == {"full_name": "Аня"}
    assert "cookie" not in {k.lower() for k in msg["headers"]}  # the panel session never reaches the agent
    assert msg["headers"]["x-jobbot"] == "1"
    assert r.status_code == 200 and r.json() == {"running": False}
    assert "evil" not in r.headers.get("set-cookie", "")  # the agent can't set cookies on the panel


def test_users_cannot_reach_each_others_agents():
    a = signup(panel(), "a@x.kz")
    b = signup(panel(), "b@x.kz")
    with a.websocket_connect("/agent/ws", headers={"authorization": "Bearer " + paired_token(a)}):
        assert b.get("/api/status").status_code == 503
        assert b.get("/relay/me").json()["online"] is False


def test_unlinking_an_agent_disconnects_it():
    c = signup(panel())
    token = paired_token(c)
    agent_id = c.get("/relay/me").json()["agents"][0]["id"]
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/agent/ws", headers={"authorization": "Bearer " + token}) as ws:
            c.post(f"/relay/agents/{agent_id}/delete")
            ws.receive_text()
    assert store.agent_by_token(token) is None


# ---------- agent side ----------
@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_agent_handles_requests_through_local_checks():
    import agent
    import app as kolenke
    ok = await agent.handle(kolenke.app, {"method": "GET", "path": "/api/status", "headers": {}, "body": ""})
    assert ok["status"] == 200 and "running" in json.loads(base64.b64decode(ok["body"]))
    outside = await agent.handle(kolenke.app, {"method": "GET", "path": "/", "headers": {}, "body": ""})
    assert outside["status"] == 403  # the panel can reach the API only
    no_header = await agent.handle(kolenke.app, {"method": "POST", "path": "/api/jobs/stop", "headers": {}, "body": ""})
    assert no_header["status"] == 403  # the local protection still applies to relayed requests


# ---------- end to end: real panel + real agent process ----------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(port)


def test_end_to_end_phone_to_agent(tmp_path):
    env = {**os.environ, "RELAY_DATA": str(tmp_path / "relay"), "JOBBOT_DATA": str(tmp_path / "agent"),
           "JOBBOT_NO_BACKGROUND": "1", "KOLENKE_PORT": str(free_port())}
    rport = free_port()
    panel_url = f"http://127.0.0.1:{rport}"
    relay_p = subprocess.Popen([sys.executable, "-m", "uvicorn", "relay.app:app", "--port", str(rport)], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    agent_p = None
    try:
        wait_port(rport)
        invite = subprocess.run([sys.executable, "-m", "relay.manage", "invite"], cwd=ROOT, env=env, capture_output=True, text=True).stdout.strip()
        phone = httpx.Client(base_url=panel_url, headers={"X-JobBot": "1"})
        assert phone.post("/auth/register", json={"email": "me@x.kz", "password": "password1", "invite": invite}).status_code == 200
        code = phone.post("/relay/pair-code").json()["code"]
        paired = subprocess.run([sys.executable, "agent.py", "pair", panel_url, code], cwd=ROOT, env=env, capture_output=True, text=True)
        assert "привязан к me@x.kz" in paired.stdout, paired.stderr
        assert oct((tmp_path / "agent" / "agent.json").stat().st_mode)[-3:] == "600"  # the token file is private

        agent_p = subprocess.Popen([sys.executable, "agent.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if phone.get("/relay/me").json()["online"]:
                break
            time.sleep(0.1)
        r = phone.get("/api/status")
        assert r.status_code == 200 and r.json()["running"] is False  # answered by kolenke on the "computer"
        assert phone.post("/api/settings", json={"full_name": "Через панель"}).status_code == 200
        assert phone.get("/api/settings").json()["full_name"] == "Через панель"
        agent_state = httpx.get(f"http://127.0.0.1:{env['KOLENKE_PORT']}/api/agent").json()
        assert agent_state["connected"] and "token" not in agent_state

        agent_p.terminate()
        agent_p.wait(5)
        for _ in range(50):
            if not phone.get("/relay/me").json()["online"]:
                break
            time.sleep(0.1)
        assert phone.get("/api/status").json()["code"] == "agent_offline"
    finally:
        for p in (agent_p, relay_p):
            if p and p.poll() is None:
                p.terminate()
                p.wait(5)
