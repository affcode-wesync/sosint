from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
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


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
