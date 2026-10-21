"""Check the running local gateway using its seeded accounts, without changing passwords."""

import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:5173"


def request(client, path, expected=200, payload=None):
    headers = {"X-Requested-With": "local-smoke"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    try:
        response = client.open(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.status == expected, (path, response.status, body[:200])
        return body


client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
assert json.loads(request(client, "/api/v1/health")) == {"status": "ok"}
assert b"<div id=\"root\"" in request(client, "/login")
assert b"<div id=\"root\"" in request(client, "/admin")
request(client, "/api/v1/does-not-exist", 404)
request(client, "/media/hls/anonymous/master.m3u8", 401)
credentials = json.loads((ROOT / ".local" / "credentials.json").read_text())
# Temporary admin/learner passwords may already have been changed by the user.
# Use only the synthetic employee for this repeatable development check.
account = credentials["synthetic_users"]
request(client, "/api/v1/auth/login", payload={
    "username": account["example_username"], "password": account["password"],
})
request(client, "/api/v1/me/dashboard")
modules = json.loads(request(client, "/api/v1/me/modules"))
core = next(module for module in modules if module["type"] == "core")
detail = json.loads(request(client, f"/api/v1/me/modules/{core['id']}"))
lesson = json.loads(request(client, f"/api/v1/me/lessons/{detail['lessons'][0]['id']}"))
media_url = lesson["hls_url"]
assert request(client, media_url).startswith(b"#EXTM3U")
for path in ("/media/originals/private.mp4", "/media/hls/%2e%2e/%2e%2e/config.json"):
    request(client, path, 404)
request(client, "/api/v1/auth/logout", 204, payload={})
request(client, media_url, 401)
print("Smoke checks passed: UI, API, learner dashboard, assigned HLS, path protection and logout revocation.")
