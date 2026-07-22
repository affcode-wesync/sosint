from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel
from typing import Optional
from analyzer import analyze_email, EmailAnalysisResult, hlr_lookup, HLRResult, sherlock_search, SherlockResult
import os

app = FastAPI(title="Email Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmailRequest(BaseModel):
    email: str


class PhoneRequest(BaseModel):
    phone: str
    api_key: str = ""


class UsernameRequest(BaseModel):
    username: str


class ExportRequest(BaseModel):
    username: str
    found: list[dict] = []
    not_found: list[str] = []
    search_time: float = 0


class EmailExportRequest(BaseModel):
    email: str = ""
    domain: str = ""
    is_gmail: bool = False
    smtp: dict = {}
    google: dict = {}
    connections: list[dict] = []
    whois: dict = {}
    risk_score: int = 0
    risk_level: str = ""
    analysis_timestamp: str = ""


class HLRExportRequest(BaseModel):
    phone: str = ""
    country: Optional[str] = ""
    region: Optional[str] = ""
    operator: Optional[str] = ""
    status: Optional[str] = ""
    mnc: Optional[str] = ""
    imsi: Optional[str] = ""
    imei: Optional[str] = ""
    ported: Optional[str] = ""
    roaming: Optional[str] = ""
    raw_response: Optional[str] = ""
    error: Optional[str] = ""


@app.post("/api/analyze", response_model=EmailAnalysisResult)
async def analyze(request: EmailRequest):
    if not request.email or "@" not in request.email:
        raise HTTPException(status_code=400, detail="Invalid email format")
    return await analyze_email(request.email)


@app.post("/api/hlr", response_model=HLRResult)
async def hlr(request: PhoneRequest):
    if not request.phone:
        raise HTTPException(status_code=400, detail="Phone number required")
    return await hlr_lookup(request.phone, request.api_key)


@app.post("/api/sherlock", response_model=SherlockResult)
async def sherlock(request: UsernameRequest):
    if not request.username:
        raise HTTPException(status_code=400, detail="Username required")
    return await sherlock_search(request.username)


@app.post("/api/sherlock/export")
async def sherlock_export(request: ExportRequest):
    if not request.username:
        raise HTTPException(status_code=400, detail="Username required")

    # Use cached results if provided, otherwise run search
    if request.found or request.not_found:
        found = request.found
        not_found = request.not_found
        search_time = request.search_time
    else:
        result = await sherlock_search(request.username)
        found = result.found
        not_found = result.not_found
        search_time = result.search_time

    template_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "reports", "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    total = len(found) + len(not_found)
    now = __import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')

    template = template.replace('id="nickValue">—', f'id="nickValue">{request.username}')
    template = template.replace('id="totalValue">0', f'id="totalValue">{total}')
    template = template.replace('id="foundValue">0', f'id="foundValue">{len(found)}')
    template = template.replace('id="timeValue">0.0s', f'id="timeValue">{search_time}s')
    template = template.replace('>РЕЗУЛЬТАТЫ<', f'>РЕЗУЛЬТАТЫ ДЛЯ: {request.username.upper()}<')

    found_rows = ""
    for item in found:
        found_rows += f'<tr><td><b>{item["site"]}</b></td><td><a href="{item["url"]}" target="_blank" rel="noopener">{item["url"]}</a></td><td><span class="found">Найден</span></td></tr>\n'

    nf_rows = ""
    for site in not_found:
        nf_rows += f'<tr><td><b>{site}</b></td><td>—</td><td><span class="nf">Не найден</span></td></tr>\n'

    template = template.replace('<tbody id="foundBody"></tbody>', f'<tbody id="foundBody">{found_rows}</tbody>')
    template = template.replace('<tbody id="nfBody"></tbody>', f'<tbody id="nfBody">{nf_rows}</tbody>')
    template = template.replace('<span id="nfCount">0</span>', f'<span id="nfCount">{len(not_found)}</span>')

    return Response(
        content=template,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="nick_report_{request.username}.html"'}
    )


@app.post("/api/analyze/export")
async def analyze_export(request: EmailExportRequest):
    if not request.email:
        raise HTTPException(status_code=400, detail="Email required")

    template_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "reports", "email_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    now = __import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')
    smtp = request.smtp
    connections = request.connections
    google = request.google

    template = template.replace('id="reportEmail">—', f'id="reportEmail">{request.email}')
    template = template.replace('id="reportDomain">—', f'id="reportDomain">{request.domain}')
    template = template.replace('id="reportSmtp">—', f'id="reportSmtp">{smtp.get("final_status", "—")}')
    template = template.replace('id="reportRisk">—', f'id="reportRisk">{request.risk_level} ({request.risk_score}/100)')
    template = template.replace('id="reportServices">0', f'id="reportServices">{len(connections)}')
    template = template.replace('>—<', f'>{now}<', 1)

    smtp_rows = ""
    for step in smtp.get("steps", []):
        smtp_rows += f'<tr><td>{step.get("step", "")}</td><td>{step.get("code", "")}</td></tr>\n'
    if not smtp_rows:
        smtp_rows = '<tr><td colspan="2">Нет данных</td></tr>'
    template = template.replace('<tbody id="smtpBody"></tbody>', f'<tbody id="smtpBody">{smtp_rows}</tbody>')

    if request.is_gmail and google:
        template = template.replace('id="profileSection" style="display:none"', 'id="profileSection"')
        profile_html = '<table style="width:100%;font-size:13px">'
        if google.get("avatar_url"):
            profile_html += f'<tr><td><img src="{google["avatar_url"]}" style="width:80px;height:80px;border-radius:4px;border:1px solid #ccc"></td>'
            profile_html += f'<td style="vertical-align:top;padding-left:12px">'
        else:
            profile_html += '<tr><td colspan="2">'
        profile_html += f'<b>Google ID:</b> {google.get("google_id", "—")}<br>'
        profile_html += f'<b>Last Update:</b> {google.get("last_update", "—")}<br>'
        if google.get("services"):
            profile_html += '<b>Services:</b><br>'
            for svc in google["services"]:
                profile_html += f'&nbsp;&nbsp;· <a href="{svc.get("url", "#")}" target="_blank">{svc.get("name", "")}</a><br>'
        profile_html += '</td></tr></table>'
        template = template.replace('<div style="padding:12px" id="profileBody"></div>', f'<div style="padding:12px" id="profileBody">{profile_html}</div>')

    conn_rows = ""
    for c in connections:
        status_class = "badge-ok" if c.get("status") == "found" else ("badge-err" if c.get("status") == "not_found" else "badge-info")
        conn_rows += f'<tr><td><b>{c.get("service", "")}</b></td><td style="font-size:11px">{c.get("url", "")}</td><td><span class="badge {status_class}">{c.get("status", "")}</span></td></tr>\n'
    if not conn_rows:
        conn_rows = '<tr><td colspan="3">Нет данных</td></tr>'
    template = template.replace('<tbody id="connectionsBody"></tbody>', f'<tbody id="connectionsBody">{conn_rows}</tbody>')

    risk_color = "#28a745" if request.risk_score < 20 else ("#ffc107" if request.risk_score < 40 else ("#fd7e14" if request.risk_score < 60 else "#dc3545"))
    risk_html = f'<div class="risk-bar"><div class="risk-fill" style="width:{request.risk_score}%;background:{risk_color}">{request.risk_score}/100 — {request.risk_level}</div></div>'
    template = template.replace('<div style="padding:12px" id="riskBody"></div>', f'<div style="padding:12px" id="riskBody">{risk_html}</div>')

    return Response(
        content=template,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="email_report_{request.email.replace("@","_at_")}.html"'}
    )


@app.post("/api/hlr/export")
async def hlr_export(request: HLRExportRequest):
    if not request.phone:
        raise HTTPException(status_code=400, detail="Phone required")

    template_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "reports", "hlr_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    now = __import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')

    template = template.replace('id="reportPhone">—', f'id="reportPhone">{request.phone}')
    template = template.replace('id="reportCountry">—', f'id="reportCountry">{request.country or "—"}')
    template = template.replace('id="reportOperator">—', f'id="reportOperator">{request.operator or "—"}')
    template = template.replace('id="reportStatus">—', f'id="reportStatus">{request.status or "—"}')

    fields = [
        ("Телефон", request.phone),
        ("Страна", request.country),
        ("Регион", request.region),
        ("Оператор", request.operator),
        ("Статус", request.status),
        ("MNC", request.mnc),
        ("IMSI", request.imsi),
        ("IMEI", request.imei),
        ("Ported", request.ported),
        ("Roaming", request.roaming),
    ]

    detail_rows = ""
    for label, value in fields:
        if value:
            detail_rows += f'<tr><td><b>{label}</b></td><td>{value}</td></tr>\n'
    if not detail_rows:
        detail_rows = '<tr><td colspan="2">Нет данных</td></tr>'
    template = template.replace('<tbody id="detailsBody"></tbody>', f'<tbody id="detailsBody">{detail_rows}</tbody>')

    if request.raw_response:
        template = template.replace('id="rawSection" style="display:none"', 'id="rawSection"')
        raw = request.raw_response[:2000]
        template = template.replace('<div class="code" id="rawBody"></div>', f'<div class="code" id="rawBody">{raw}</div>')

    return Response(
        content=template,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="hlr_report_{request.phone}.html"'}
    )


@app.get("/api/auth/status")
async def auth_status():
    from auth import get_credentials
    creds = get_credentials()
    return {"authenticated": creds is not None and creds.valid}


@app.get("/api/auth/url")
async def auth_url():
    from google_auth_oauthlib.flow import InstalledAppFlow
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if not os.path.exists(credentials_path):
        return {"error": "credentials.json not found", "url": None}
    flow = InstalledAppFlow.from_client_secrets_file(
        credentials_path,
        ['https://www.googleapis.com/auth/userinfo.profile']
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return {"url": auth_url}


@app.get("/api/auth/callback")
async def auth_callback(code: str = None):
    if not code:
        return HTMLResponse("<h1>Error: No code provided</h1>")
    return HTMLResponse("<h1>Authorization complete! You can close this window.</h1>")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ===== Auth System =====
import json
import secrets
from datetime import datetime

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")
ADMIN_KEY = "67zovpokoyo"

def load_keys():
    if not os.path.exists(KEYS_FILE):
        return {"admin_key": ADMIN_KEY, "keys": []}
    with open(KEYS_FILE, "r") as f:
        return json.load(f)

def save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_client_ip(request):
    return request.client.host if request.client else "unknown"


class LoginRequest(BaseModel):
    key: str

class KeyCreateRequest(BaseModel):
    username: str = ""
    comment: str = ""

class KeyManageRequest(BaseModel):
    key: str
    action: str  # "block", "unblock", "delete"


@app.post("/api/auth/login")
async def auth_login(request: LoginRequest, req: Request = None):
    data = load_keys()

    # Check admin key
    if request.key == data.get("admin_key"):
        return {"status": "ok", "role": "admin", "message": "Admin access granted"}

    # Check user keys
    for k in data.get("keys", []):
        if k["key"] == request.key and k.get("status") == "active":
            k["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            k["login_count"] = k.get("login_count", 0) + 1
            save_keys(data)
            return {"status": "ok", "role": "user", "username": k.get("username", ""), "message": "Access granted"}

    raise HTTPException(status_code=401, detail="Invalid key")


@app.post("/api/auth/admin/check")
async def auth_admin_check(request: LoginRequest):
    data = load_keys()
    if request.key == data.get("admin_key"):
        return {"status": "ok", "is_admin": True}
    raise HTTPException(status_code=401, detail="Admin access denied")


@app.get("/api/auth/admin/keys")
async def auth_admin_get_keys(key: str = ""):
    data = load_keys()
    if key != data.get("admin_key"):
        raise HTTPException(status_code=401, detail="Admin access denied")
    return {"keys": data.get("keys", [])}


@app.post("/api/auth/admin/keys/create")
async def auth_admin_create_key(request: KeyCreateRequest, key: str = ""):
    data = load_keys()
    if key != data.get("admin_key"):
        raise HTTPException(status_code=401, detail="Admin access denied")

    new_key = secrets.token_urlsafe(16)
    entry = {
        "key": new_key,
        "username": request.username,
        "comment": request.comment,
        "status": "active",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_login": None,
        "login_count": 0
    }
    data.setdefault("keys", []).append(entry)
    save_keys(data)
    return {"status": "ok", "key": new_key, "message": "Key created"}


@app.post("/api/auth/admin/keys/manage")
async def auth_admin_manage_key(request: KeyManageRequest, key: str = ""):
    data = load_keys()
    if key != data.get("admin_key"):
        raise HTTPException(status_code=401, detail="Admin access denied")

    keys = data.get("keys", [])
    target = None
    for k in keys:
        if k["key"] == request.key:
            target = k
            break

    if not target:
        raise HTTPException(status_code=404, detail="Key not found")

    if request.action == "block":
        target["status"] = "blocked"
    elif request.action == "unblock":
        target["status"] = "active"
    elif request.action == "delete":
        data["keys"] = [k for k in keys if k["key"] != request.key]
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    save_keys(data)
    return {"status": "ok", "message": f"Key {request.action}ed"}


@app.post("/api/auth/admin/change_password")
async def auth_admin_change_password(request: LoginRequest, key: str = ""):
    data = load_keys()
    if key != data.get("admin_key"):
        raise HTTPException(status_code=401, detail="Admin access denied")
    if not request.key or len(request.key) < 4:
        raise HTTPException(status_code=400, detail="Password too short")
    data["admin_key"] = request.key
    save_keys(data)
    return {"status": "ok", "message": "Admin password changed"}


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
map_dir = os.path.join(os.path.dirname(__file__), "..", "sosint-map")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
app.mount("/map", StaticFiles(directory=map_dir), name="static-map")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
