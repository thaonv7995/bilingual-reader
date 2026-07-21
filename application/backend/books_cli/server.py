import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from books_core.repo import default_library_root, books_dir, repo_root
from books_core.ingest import ingest_epub, ingest_pdf
from books_core.paths import BookPaths
from books_core.meta.reader import book_overview_summary, book_status_summary
from books_core.package import pack_book
from books_core.asset_paths import normalize_per_page_asset_paths
from books_core.validation import draft_html_file_valid
from books_core.repair_report import read_repair_report
from books_core.page_editor import (
    list_stylesheet_sources,
    read_page_source,
    read_stylesheet_source,
    save_page_source,
    save_stylesheet_source,
    validate_page_source,
    validate_stylesheet_source,
)
from books_cli.agy_settings import (
    credential_paths,
    credentials_present,
    extract_oauth_url,
    parse_quota_output,
    remove_credentials,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("books_server")

app = FastAPI(title="Bilingual Reader Book Studio")

PREVIEW_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "CDN-Cache-Control": "no-store",
    "Pragma": "no-cache",
}


def _preview_file(root: Path, rest_of_path: str) -> Path | None:
    """Resolve one preview file without allowing traversal outside its root."""
    root = root.resolve()
    candidate = (root / rest_of_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _preview_not_found(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": message},
        headers=PREVIEW_NO_CACHE_HEADERS,
    )


def _valid_preview_segment(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value or ""))


def _preview_asset_response(slug: str, rest_of_path: str) -> FileResponse | JSONResponse:
    if not _valid_preview_segment(slug):
        return _preview_not_found("Asset not found")
    root = books_dir() / slug / "output" / "assets"
    actual_path = _preview_file(root, rest_of_path)
    if actual_path is None:
        return _preview_not_found("Asset not found")
    return FileResponse(actual_path, headers=PREVIEW_NO_CACHE_HEADERS)


# --- No-cache routes for standalone pages and Studio iframe preview ---
@app.get("/books/{slug}/output/assets/{rest_of_path:path}")
async def serve_output_assets(slug: str, rest_of_path: str):
    return _preview_asset_response(slug, rest_of_path)


@app.get("/books/{slug}/output/{lang}/assets/{rest_of_path:path}")
async def serve_preview_assets(slug: str, lang: str, rest_of_path: str):
    return _preview_asset_response(slug, rest_of_path)


@app.get("/books/{slug}/preview-assets/{version}/{rest_of_path:path}")
async def serve_versioned_preview_assets(
    slug: str,
    version: str,
    rest_of_path: str,
):
    if not _valid_preview_segment(version):
        return _preview_not_found("Asset not found")
    return _preview_asset_response(slug, rest_of_path)


@app.get("/books/{slug}/preview/{version}/{lang}/page_{page_num:int}.html")
async def serve_versioned_preview_page(
    slug: str,
    version: str,
    lang: str,
    page_num: int,
):
    if not all(
        _valid_preview_segment(value)
        for value in (slug, version, lang)
    ):
        return _preview_not_found("Page not found")
    page_root = books_dir() / slug / "output" / lang
    page_path = _preview_file(page_root, f"page_{page_num:04d}.html")
    if page_path is None:
        return _preview_not_found("Page not found")

    html = normalize_per_page_asset_paths(page_path.read_text(encoding="utf-8"))
    versioned_assets = f"/books/{slug}/preview-assets/{version}/"
    html = html.replace("../assets/", versioned_assets)
    return HTMLResponse(html, headers=PREVIEW_NO_CACHE_HEADERS)

app.mount("/books", StaticFiles(directory=str(books_dir())), name="books")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <defs>
            <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#3b82f6"/>
                <stop offset="100%" stop-color="#8b5cf6"/>
            </linearGradient>
        </defs>
        <rect width="100%" height="100%" fill="none"/>
        <path d="M20 25 C 20 15, 45 15, 50 25 C 55 15, 80 15, 80 25 L 80 80 C 80 70, 55 70, 50 80 C 45 70, 20 70, 20 80 Z" fill="url(#g)"/>
        <path d="M50 25 L 50 80" stroke="#ffffff" stroke-width="3" opacity="0.3"/>
    </svg>"""
    return Response(content=svg, media_type="image/svg+xml")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/studio/login":
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = request.query_params.get("token")
            
        expected_token = os.environ.get("STUDIO_SESSION_TOKEN", "studio_session_secret_token_123")
        if not token or token != expected_token:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Unauthorized"}
            )
            
    response = await call_next(request)
    return response

class StudioLoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/studio/login")
def studio_login(data: StudioLoginRequest):
    expected_user = os.environ.get("STUDIO_USERNAME", "admin")
    expected_pass = os.environ.get("STUDIO_PASSWORD", "admin")
    if data.username == expected_user and data.password == expected_pass:
        token = os.environ.get("STUDIO_SESSION_TOKEN", "studio_session_secret_token_123")
        return {"success": True, "token": token}
    raise HTTPException(status_code=401, detail="Invalid username or password")

# Global session configurations
class ProcessConfig(BaseModel):
    threads: int = 4
    translate: bool = True
    force: bool = False
    pages: Optional[str] = None
    custom_prompt: Optional[str] = None


class PageEditorPayload(BaseModel):
    lang: str = "en"
    html: str
    revision: Optional[str] = None


class StylesheetEditorPayload(BaseModel):
    css: str
    revision: Optional[str] = None

# Cache for active tasks and logs
# slug -> asyncio.subprocess.Process
running_processes: Dict[str, asyncio.subprocess.Process] = {}
# Slugs reserved while asyncio.create_subprocess_exec is still awaiting. Without
# this reservation, concurrent clicks/requests can all pass the running check.
starting_processes: set[str] = set()
# slug -> list of string logs
process_logs: Dict[str, List[str]] = {}
# Long PDF exports run outside request lifetimes and publish progress via status.
pdf_export_tasks: Dict[str, asyncio.Task] = {}
pdf_export_status: Dict[str, dict] = {}
# Upload requests must return before EPUB conversion / PDF splitting finishes,
# otherwise reverse proxies can terminate the request with a 524 timeout.
upload_tasks: Dict[str, asyncio.Task] = {}
upload_jobs: Dict[str, dict] = {}

# --- Caching Layer to prevent massive disk scanning lag ---
class ResponseCache:
    def __init__(self):
        self.library_cache = None
        self.library_cache_time = 0.0
        self.status_cache = {}  # slug -> (timestamp, data)

    def get_library(self, ttl=4.0):
        now = time.time()
        if self.library_cache is not None and (now - self.library_cache_time < ttl):
            return self.library_cache
        return None

    def set_library(self, data):
        self.library_cache = data
        self.library_cache_time = time.time()

    def get_status(self, slug, ttl=2.0):
        now = time.time()
        if slug in self.status_cache:
            ts, data = self.status_cache[slug]
            if now - ts < ttl:
                return data
        return None

    def set_status(self, slug, data):
        self.status_cache[slug] = (time.time(), data)

    def clear(self, slug=None):
        self.library_cache = None
        self.library_cache_time = 0.0
        if slug:
            self.status_cache.pop(slug, None)
        else:
            self.status_cache.clear()

response_cache = ResponseCache()

class LoginSession:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.oauth_url: Optional[str] = None
        self.logs: List[str] = []
        self.status: str = "idle"  # idle, starting, waiting_url, waiting_browser, waiting_code, verifying, success, failed
        self.requires_code: bool = False
        self.url_file: Optional[Path] = None

# Singleton login session
login_session = LoginSession()

def get_agy_binary() -> str:
    for path in ["/Users/thaonv/.local/bin/agy", "agy"]:
        if shutil.which(path):
            return path
    return "agy"

def get_token_paths() -> list[Path]:
    return credential_paths()

# --- Persistent Studio State Database (JSON Store) ---
class StudioState:
    def __init__(self):
        self.state_file = books_dir() / "studio-state.json"
        self.data = {
            "auth": {
                "logged_in": False,
                "email": None,
                "last_checked": 0.0
            },
            "books": {}
        }
        self.load()

    def load(self):
        if self.state_file.is_file():
            try:
                content = self.state_file.read_text(encoding="utf-8")
                loaded_data = json.loads(content)
                if "auth" in loaded_data:
                    self.data["auth"].update(loaded_data["auth"])
                if "books" in loaded_data:
                    # Update each book metadata
                    for slug, info in loaded_data["books"].items():
                        if slug not in self.data["books"]:
                            self.data["books"][slug] = {}
                        self.data["books"][slug].update(info)
            except Exception as e:
                logger.error(f"Failed to load studio-state.json: {e}")

    def save(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save studio-state.json: {e}")

    def update_auth(self, logged_in: bool, email: Optional[str] = None):
        self.data["auth"]["logged_in"] = logged_in
        if email:
            self.data["auth"]["email"] = email
        elif not logged_in:
            self.data["auth"]["email"] = None
        self.data["auth"]["last_checked"] = time.time()
        self.save()

    def update_book_process(self, slug: str, status: str, threads: int, translate: bool, logs: List[str]):
        if slug not in self.data["books"]:
            self.data["books"][slug] = {}
        self.data["books"][slug].update({
            "status": status,
            "threads": threads,
            "translate": translate,
            "logs": logs,
            "last_processed": time.time()
        })
        self.save()

    def update_library_states(self, slugs: list[str], library_state: str) -> None:
        for slug in slugs:
            if slug not in self.data["books"]:
                self.data["books"][slug] = {}
            self.data["books"][slug]["library_state"] = library_state
        self.save()

    def reset_book(self, slug: str) -> None:
        self.data["books"][slug] = {"library_state": "active"}
        self.save()

    def remove_book(self, slug: str) -> None:
        if self.data["books"].pop(slug, None) is not None:
            self.save()

    def get_book_process(self, slug: str) -> dict:
        defaults = {
            "status": "idle",
            "threads": 4,
            "translate": True,
            "logs": [],
            "last_processed": 0.0,
            "library_state": "active",
        }
        defaults.update(self.data["books"].get(slug, {}))
        return defaults

# Instantiate singleton persistent state
studio_state = StudioState()

def find_logged_in_email() -> Optional[str]:
    return studio_state.data["auth"].get("email")

_auth_cache = {
    "state": "checking",
    "logged_in": False,
    "email": None,
    "message": "Checking AGY CLI session…",
    "last_check": 0.0,
}


def _set_auth_state(state: str, *, email: str | None = None, message: str | None = None) -> None:
    logged_in = state == "connected"
    _auth_cache.update(
        {
            "state": state,
            "logged_in": logged_in,
            "email": email,
            "message": message or "",
            "last_check": time.time(),
        }
    )
    studio_state.update_auth(logged_in=logged_in, email=email)


def _reset_agy_caches(*, state: str = "checking", message: str = "Checking AGY CLI session…") -> None:
    _set_auth_state(state, email=None, message=message)
    _quota_cache.update({"data": None, "last_updated": 0.0, "is_updating": False})

def is_agy_authenticated(force: bool = False) -> bool:
    """Return readiness from the last interactive probe.

    ``agy models`` is intentionally not used here: it lists models even when
    OAuth credentials are absent or the account still needs verification.
    """
    return bool(_auth_cache["state"] == "connected")
# Quota memory cache
_quota_cache = {
    "data": None,
    "last_updated": 0.0,
    "is_updating": False
}

async def refresh_quota_cache_async():
    global _quota_cache
    if _quota_cache["is_updating"]:
        return
    # AGY 1.1.3 stores OAuth in the OS keyring instead of the legacy token
    # files. The interactive probe is therefore the source of truth; do not
    # reject the request solely because no credential file is visible.
    _quota_cache["is_updating"] = True
    proc = None
    try:
        agy_bin = get_agy_binary()
        script_path = str(Path(repo_root()) / "fetch_quota_tmux.sh")
        probe_env = dict(os.environ)
        capture_bin_dir = str(Path(__file__).parent / "bin")
        probe_env["BROWSER"] = str(Path(capture_bin_dir) / "open")
        probe_env["PATH"] = f"{capture_bin_dir}{os.pathsep}{probe_env.get('PATH', '')}"

        proc = await asyncio.create_subprocess_exec(
            script_path, agy_bin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=probe_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        
        if proc.returncode == 0:
            output = stdout.decode('utf-8', errors='replace')
            parsed = parse_quota_output(output)
            state = parsed["state"]
            quota = parsed["quota"]
            email = quota.get("account") or None
            _set_auth_state(state, email=email, message=parsed["message"])

            if parsed["raw_has_quota"]:
                _quota_cache["data"] = {
                    "success": True,
                    "quota": quota,
                    "state": state,
                    "warning": parsed["message"] if state != "connected" else None,
                }
                _quota_cache["last_updated"] = time.time()
            else:
                _quota_cache["data"] = {
                    "success": False,
                    "error": parsed["message"],
                    "state": state,
                }
                _quota_cache["last_updated"] = time.time()
        else:
            error = stderr.decode('utf-8', errors='replace').strip() or "Failed to retrieve quota"
            _set_auth_state("error", message=error)
            _quota_cache["data"] = {"success": False, "error": error, "state": "error"}
            _quota_cache["last_updated"] = time.time()
    except asyncio.TimeoutError:
        _set_auth_state("error", message="AGY quota check timed out.")
        _quota_cache["data"] = {"success": False, "error": "AGY quota check timed out", "state": "error"}
        _quota_cache["last_updated"] = time.time()
    except Exception as e:
        logger.error(f"Error updating quota cache: {e}")
        _set_auth_state("error", message=f"AGY quota check failed: {e}")
        _quota_cache["data"] = {"success": False, "error": f"AGY quota check failed: {str(e)}", "state": "error"}
        _quota_cache["last_updated"] = time.time()
    finally:
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
        _quota_cache["is_updating"] = False

async def background_quota_updater():
    await asyncio.sleep(5)
    while True:
        try:
            age = time.time() - _quota_cache["last_updated"]
            if _auth_cache["state"] != "disconnected" and (
                _quota_cache["data"] is None or age >= 120
            ):
                await refresh_quota_cache_async()
        except Exception as e:
            logger.error(f"Error in background quota updater: {e}")
        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_quota_updater())

@app.get("/api/auth/status")
async def get_auth_status(force: bool = False):
    if force:
        await refresh_quota_cache_async()
    elif (
        _auth_cache["state"] != "disconnected"
        and _quota_cache["data"] is None
        and not _quota_cache["is_updating"]
    ):
        asyncio.create_task(refresh_quota_cache_async())
    return {
        "logged_in": _auth_cache["state"] == "connected",
        "credential_present": credentials_present(),
        "state": _auth_cache["state"],
        "message": _auth_cache["message"],
        "email": _auth_cache.get("email") or studio_state.data["auth"].get("email"),
        "login_status": login_session.status,
        "oauth_url": login_session.oauth_url,
        "checking": _auth_cache["state"] == "checking" or _quota_cache["is_updating"],
    }

@app.get("/api/auth/quota")
async def get_auth_quota(force: bool = False):
    global _quota_cache
    import time
    now = time.time()

    # Do not repeatedly start AGY (which may itself launch browser auth) after
    # an explicit logout. A forced refresh remains available for sessions that
    # were authenticated outside Studio.
    if _auth_cache["state"] == "disconnected" and not force:
        return {
            "success": False,
            "error": "AGY CLI is not signed in.",
            "state": "disconnected",
        }
    
    if force:
        await refresh_quota_cache_async()
    elif (_quota_cache["data"] is None or now - _quota_cache["last_updated"] > 120) and not _quota_cache["is_updating"]:
        if _quota_cache["data"] is None:
            await refresh_quota_cache_async()
        else:
            asyncio.create_task(refresh_quota_cache_async())
            
    if _quota_cache["data"] is not None:
        res = dict(_quota_cache["data"])
        res["age"] = int(time.time() - _quota_cache["last_updated"])
        return res
        
    return {"success": False, "error": "Quota cache is being populated, please wait a moment."}
@app.post("/api/auth/logout_agy")
async def logout_agy_cli():
    global login_session
    cli_warning = None
    try:
        if login_session.process and login_session.process.returncode is None:
            login_session.process.kill()
            await login_session.process.wait()
        login_session = LoginSession()

        script_path = Path(repo_root()) / "logout_agy.exp"
        if script_path.exists() and shutil.which("expect"):
            agy_bin = get_agy_binary()
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["expect", str(script_path), agy_bin],
                    timeout=25,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    cli_warning = "AGY CLI did not confirm remote logout; local credentials were cleared."
            except Exception as e:
                cli_warning = f"Remote logout check failed; local credentials were cleared: {e}"

        remove_credentials()
        _reset_agy_caches(state="disconnected", message="AGY CLI is not signed in.")
        return {"success": True, "state": "disconnected", "warning": cli_warning}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/auth/login")
async def start_auth_login():
    global login_session
    
    if _auth_cache["state"] == "connected":
        return {"success": True, "already_authenticated": True, "state": "connected"}
        
    # Terminate any existing login process
    if login_session.process and login_session.process.returncode is None:
        try:
            login_session.process.kill()
            await login_session.process.wait()
        except Exception:
            pass
    if login_session.url_file:
        login_session.url_file.unlink(missing_ok=True)

    # A stale or ineligible token makes AGY skip the login chooser. Reconnect is
    # an explicit user action, so clear only local OAuth credentials before
    # starting a fresh authorization flow.
    remove_credentials()
    _reset_agy_caches(state="disconnected", message="Waiting for AGY authorization.")
            
    login_session = LoginSession()
    login_session.status = "starting"
    
    agy_bin = get_agy_binary()
    logger.info(f"Spawning '{agy_bin} login' to fetch OAuth link")
    
    import tempfile
    url_fd, url_file = tempfile.mkstemp(prefix="agy_oauth_")
    os.close(url_fd)
    Path(url_file).unlink(missing_ok=True)
    login_session.url_file = Path(url_file)
    
    try:
        script_path = Path(repo_root()) / "login_agy.exp"
        if not shutil.which("expect"):
            raise RuntimeError("The 'expect' command is required for AGY browser login.")
        env = dict(os.environ)
        env["AGY_OAUTH_URL_FILE"] = url_file
        env.setdefault("TERM", "xterm-256color")
        env["NO_COLOR"] = "1"
        env["COLUMNS"] = "1000"
        env["LINES"] = "100"
        # Capture browser launches instead of opening a browser on the server.
        dummy_bin_dir = str(Path(__file__).parent / "bin")
        env["BROWSER"] = str(Path(dummy_bin_dir) / "open")
        env["PATH"] = f"{dummy_bin_dir}{os.pathsep}{env.get('PATH', '')}"
        
        proc = await asyncio.create_subprocess_exec(
            "expect", str(script_path), agy_bin,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        login_session.process = proc
    except Exception as e:
        login_session.status = "failed"
        logger.error(f"Failed to start agy login process: {e}")
        return {"success": False, "error": f"Failed to start agy login: {str(e)}"}

    session = login_session

    def mark_oauth_url(url: str) -> None:
        if not url.startswith("http"):
            return
        session.oauth_url = url
        session.status = "waiting_code" if session.requires_code else "waiting_browser"

    async def drain_stdout():
        while True:
            chunk_bytes = await proc.stdout.read(1024)
            if not chunk_bytes:
                break
            chunk = chunk_bytes.decode('utf-8', errors='replace')
            session.logs.append(chunk)
            combined = "".join(session.logs[-12:])
            if not session.oauth_url:
                parsed_url = extract_oauth_url(combined)
                if parsed_url:
                    mark_oauth_url(parsed_url)
            lowered = combined.lower()
            if "authorization code" in lowered or "verification code" in lowered or "paste" in lowered and "code" in lowered:
                session.requires_code = True
                if session.oauth_url:
                    session.status = "waiting_code"

    async def monitor_oauth_url():
        try:
            while proc.returncode is None and not session.oauth_url:
                if session.url_file and session.url_file.is_file():
                    captured_url = session.url_file.read_text(errors="replace").strip()
                    if captured_url.startswith("http"):
                        mark_oauth_url(captured_url)
                        break
                await asyncio.sleep(0.5)
            if proc.returncode is not None and not session.oauth_url:
                if credentials_present():
                    session.status = "success"
                    _set_auth_state("connected", message="AGY authorization completed.")
                else:
                    session.status = "failed"
        finally:
            if session.url_file:
                session.url_file.unlink(missing_ok=True)
                session.url_file = None

    asyncio.create_task(drain_stdout())
    asyncio.create_task(monitor_oauth_url())

    # Return quickly when AGY renders the link normally. If it is still
    # starting, leave the process alive and let the Settings UI poll status.
    for _ in range(16):
        if session.oauth_url or credentials_present() or proc.returncode is not None:
            break
        await asyncio.sleep(0.5)

    if session.oauth_url:
        return {
            "success": True,
            "url": session.oauth_url,
            "verification_mode": "code" if session.requires_code else "browser",
        }
    if credentials_present():
        session.status = "success"
        _set_auth_state("connected", message="AGY authorization completed.")
        return {"success": True, "already_authenticated": True, "state": "connected"}
    if proc.returncode is not None:
        session.status = "failed"
        return {
            "success": False,
            "error": "AGY exited before producing an OAuth URL.",
            "logs": "".join(session.logs),
        }

    session.status = "waiting_url"
    return {
        "success": True,
        "pending": True,
        "state": "waiting_url",
        "message": "AGY is still preparing the OAuth link.",
    }


@app.post("/api/auth/complete")
async def complete_browser_auth():
    """Check a browser-based AGY login without requiring a pasted code."""
    global login_session
    login_session.status = "verifying"
    await refresh_quota_cache_async()
    state = _auth_cache["state"]
    authorization_completed = state == "connected" or credentials_present()
    if authorization_completed:
        if state != "connected":
            _set_auth_state(
                "connected",
                email=_auth_cache.get("email"),
                message="AGY authorization completed.",
            )
            state = "connected"
        if login_session.process and login_session.process.returncode is None:
            try:
                login_session.process.kill()
                await login_session.process.wait()
            except ProcessLookupError:
                pass
        login_session.status = "success"
        return {
            "success": True,
            "state": state,
            "ready": state == "connected",
            "message": _auth_cache["message"],
            "email": _auth_cache.get("email"),
        }

    login_session.status = "waiting_browser"
    return {
        "success": False,
        "state": state,
        "error": _auth_cache["message"] or "Browser authorization has not completed yet.",
    }

@app.post("/api/auth/verify")
async def verify_auth_code(payload: dict):
    global login_session
    code = payload.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Verification code is required")
        
    if not login_session.process or login_session.process.returncode is not None:
        raise HTTPException(status_code=400, detail="No active login session")
        
    login_session.status = "verifying"
    logger.info(f"Writing authorization code to stdin")
    
    try:
        login_session.process.stdin.write(f"{code}\n".encode())
        await login_session.process.stdin.drain()
    except Exception as e:
        login_session.status = "failed"
        return {"success": False, "error": f"Failed to write to stdin: {str(e)}"}
        
    # Output is already being drained by the background task in start_auth_login
    # Just wait a bit for the process to exit after providing the code
        
    try:
        exit_code = await asyncio.wait_for(login_session.process.wait(), timeout=20.0)
    except asyncio.TimeoutError:
        try:
            login_session.process.kill()
            await login_session.process.wait()
        except Exception:
            pass
        exit_code = -1
        
    await refresh_quota_cache_async()
    has_token = credentials_present()
    state = _auth_cache["state"]
    authorization_completed = exit_code == 0 or has_token or state == "connected"
    if authorization_completed and state != "connected":
        _set_auth_state(
            "connected",
            email=_auth_cache.get("email"),
            message="AGY authorization completed.",
        )
        state = "connected"
    if authorization_completed:
        login_session.status = "success"
        return {
            "success": authorization_completed,
            "state": state,
            "ready": state == "connected",
            "message": _auth_cache["message"],
            "error": None if authorization_completed else "AGY authorization did not complete.",
        }
    else:
        login_session.status = "failed"
        return {
            "success": False, 
            "error": f"Verification exited with code {exit_code}", 
            "logs": "".join(login_session.logs)
        }

@app.post("/api/auth/cancel_login")
async def cancel_auth_login():
    global login_session
    if login_session.process and login_session.process.returncode is None:
        try:
            logger.info("Killing active agy login session due to user cancellation")
            login_session.process.kill()
            await login_session.process.wait()
        except Exception as e:
            logger.warning(f"Error killing login session: {e}")
            pass
    login_session.status = "idle"
    login_session.oauth_url = None
    login_session.process = None
    if login_session.url_file:
        login_session.url_file.unlink(missing_ok=True)
        login_session.url_file = None
    if _auth_cache["state"] != "connected":
        _reset_agy_caches(state="disconnected", message="AGY CLI is not signed in.")
    return {"success": True}

@app.get("/api/books")
def list_books_endpoint():
    has_any_running = len(running_processes) > 0
    library_ttl = 1.0 if has_any_running else 5.0
    
    cached = response_cache.get_library(library_ttl)
    if cached is not None:
        return cached

    books_folder = books_dir()
    found = []
    if books_folder.is_dir():
        for child in sorted(books_folder.iterdir()):
            if child.name.startswith("_") or child.name == "library.json":
                continue
            if child.is_dir() and BookPaths.open(child).book_json.is_file():
                try:
                    # Library cards only need inexpensive overview metadata.
                    # Per-page manifests and HTML validation belong to /status.
                    summary = book_overview_summary(BookPaths.open(child))
                    
                    # Check if packed file exists
                    bkb_path1 = books_folder / f"{child.name}.bkb"
                    bkb_path2 = books_folder / "bkbs" / f"{child.name}.bkb"
                    has_bkb = bkb_path1.is_file() or bkb_path2.is_file()
                    
                    # Persisted processing status
                    book_conf = studio_state.get_book_process(child.name)
                    persisted_status = book_conf.get("status", "idle")
                    
                    found.append({
                        "slug": child.name,
                        "title": summary.get("title") or child.name.replace("-", " ").title(),
                        "page_count": summary["page_count"],
                        "published": summary["published"],
                        "page_pdf_done": summary["page_pdf_done"],
                        "has_bkb": has_bkb,
                        "running": child.name in running_processes,
                        "status": persisted_status,
                        "library_state": book_conf.get("library_state", "active"),
                    })
                except Exception as e:
                    logger.warning(f"Error scanning book '{child.name}': {e}")
                    pass
    res = {"books": found}
    response_cache.set_library(res)
    return res


class BookLibraryStateRequest(BaseModel):
    slugs: list[str]
    state: str


@app.patch("/api/books/library-state")
def update_books_library_state(payload: BookLibraryStateRequest):
    if payload.state not in {"active", "done"}:
        raise HTTPException(status_code=422, detail="Library state must be 'active' or 'done'")
    slugs = list(dict.fromkeys(slug.strip() for slug in payload.slugs if slug.strip()))
    if not slugs:
        raise HTTPException(status_code=422, detail="Select at least one book")

    missing = [slug for slug in slugs if not (books_dir() / slug).is_dir()]
    if missing:
        raise HTTPException(status_code=404, detail=f"Books not found: {', '.join(missing)}")
    if payload.state == "done":
        running = [
            slug for slug in slugs
            if slug in running_processes or slug in starting_processes
        ]
        if running:
            raise HTTPException(
                status_code=409,
                detail=f"Stop processing before marking Done: {', '.join(running)}",
            )

    studio_state.update_library_states(slugs, payload.state)
    response_cache.clear()
    return {"success": True, "slugs": slugs, "state": payload.state}

async def _run_upload_job(job_id: str, temp_path: Path, suffix: str) -> None:
    upload_jobs[job_id].update({"status": "processing", "message": "Preparing book…"})
    try:
        if suffix == ".bkb":
            from books_core.package import unpack_book

            result = await asyncio.to_thread(unpack_book, temp_path, books_dir())
            book = {
                "slug": result["slug"],
                "title": result.get("title") or result["slug"],
            }
            if temp_path.is_file():
                temp_path.unlink()
        else:
            ingest = ingest_epub if suffix == ".epub" else ingest_pdf
            upload_jobs[job_id]["message"] = (
                "Converting EPUB to A4 pages…"
                if suffix == ".epub"
                else "Ingesting and splitting PDF…"
            )
            book = await asyncio.to_thread(ingest, temp_path)

        if suffix == ".bkb" or book.get("action") == "created":
            studio_state.reset_book(book["slug"])

        response_cache.clear()
        upload_jobs[job_id].update(
            {
                "status": "completed",
                "message": "Book is ready",
                "book": book,
                "completed_at": time.time(),
            }
        )
    except Exception as exc:
        logger.exception("Background upload ingestion failed for %s", temp_path.name)
        if temp_path.is_file():
            try:
                temp_path.unlink()
            except OSError:
                pass
        upload_jobs[job_id].update(
            {
                "status": "failed",
                "message": "Ingestion failed",
                "error": str(exc),
                "completed_at": time.time(),
            }
        )
    finally:
        # The canonical input has already been copied into the book workspace.
        # Remove this job's private staging directory on both success and failure.
        shutil.rmtree(temp_path.parent, ignore_errors=True)
        upload_tasks.pop(job_id, None)


@app.get("/api/uploads/{job_id}")
def get_upload_job(job_id: str):
    job = upload_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return job


@app.post("/api/upload", status_code=202)
async def upload_file(file: UploadFile = File(...)):
    inbox = default_library_root() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".pdf", ".epub", ".bkb"}:
        raise HTTPException(status_code=400, detail="Only PDF, EPUB, or BKB files are supported")
    job_id = uuid.uuid4().hex
    staging_dir = inbox / ".uploads" / job_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / safe_name

    logger.info(f"Saving uploaded file to {temp_path} in chunked mode")
    try:
        with open(temp_path, "wb") as f:
            while True:
                # Read file in 1MB chunks to avoid memory spikes
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        logger.error(f"Failed to write uploaded file chunk: {e}")
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"File upload write error: {str(e)}")

    # Keep a small bounded history for clients polling recently submitted jobs.
    cutoff = time.time() - 86400
    for old_id, old_job in list(upload_jobs.items()):
        if old_job.get("created_at", 0) < cutoff and old_id not in upload_tasks:
            upload_jobs.pop(old_id, None)
            shutil.rmtree(inbox / ".uploads" / old_id, ignore_errors=True)

    upload_jobs[job_id] = {
        "job_id": job_id,
        "filename": safe_name,
        "status": "queued",
        "message": "Upload complete; ingestion queued…",
        "created_at": time.time(),
    }
    task = asyncio.create_task(_run_upload_job(job_id, temp_path, suffix))
    upload_tasks[job_id] = task
    return {
        "success": True,
        "accepted": True,
        "job_id": job_id,
        "status": "queued",
    }

@app.get("/api/books/{slug}/status")
def get_book_status_endpoint(slug: str):
    is_running = slug in running_processes
    is_pdf_exporting = slug in pdf_export_tasks
    status_ttl = 1.5 if is_running or is_pdf_exporting else 5.0
    
    cached = response_cache.get_status(slug, status_ttl)
    if cached is not None:
        return cached

    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
        
    book = BookPaths.open(book_path)
    summary = book_status_summary(book)
    
    # Add translation status to pages
    pages_enriched = []
    for p in summary.get("pages", []):
        page_num = p["page"]
        en_html = book.page_lang_html(page_num, "en")
        vi_html = book.page_lang_html(page_num, "vi")
        # The UI contract names EN readiness "published" and VI readiness
        # "translated", regardless of which language was rendered first.
        p["published"] = draft_html_file_valid(en_html)
        p["translated"] = draft_html_file_valid(vi_html)
        
        # Load process.status.json if it exists to get real-time activity
        p["process_state"] = None
        p["process_step"] = None
        p["process_activity"] = None
        
        status_file = book.page_work(page_num) / "process.status.json"
        if status_file.is_file():
            try:
                status_data = json.loads(status_file.read_text(encoding="utf-8"))
                p["process_state"] = status_data.get("state")
                p["process_step"] = status_data.get("step_label") or status_data.get("step")
                p["process_activity"] = status_data.get("activity") or status_data.get("message")
            except Exception:
                pass
                
        pages_enriched.append(p)
        
    summary["pages"] = pages_enriched
    summary["published"] = sum(1 for page in pages_enriched if page.get("published"))
    summary["running"] = is_running
    
    bkb_path1 = books_dir() / f"{slug}.bkb"
    bkb_path2 = books_dir() / "bkbs" / f"{slug}.bkb"
    summary["has_bkb"] = bkb_path1.is_file() or bkb_path2.is_file()
    
    # Check if assembled book files exist
    summary["has_book_html"] = (book.output_dir / "book.html").is_file()
    summary["has_book_vi_html"] = (book.output_dir / "book.vi.html").is_file()
    summary["has_book_pdf"] = (book.output_dir / "book.pdf").is_file()
    summary["has_book_vi_pdf"] = (book.output_dir / "book.vi.pdf").is_file()
    summary["library_state"] = studio_state.get_book_process(slug).get(
        "library_state", "active"
    )
    summary["pdf_exporting"] = is_pdf_exporting
    summary["pdf_export"] = dict(pdf_export_status.get(slug, {}))
    summary["repair_report"] = read_repair_report(book.root)
    
    response_cache.set_status(slug, summary)
    return summary

async def read_subprocess_output(slug: str, process: asyncio.subprocess.Process, book_path: Path):
    try:
        line_count = 0
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='replace')
            process_logs[slug].append(decoded_line)
            line_count += 1
            # Periodically flush logs to the JSON state database
            if line_count % 15 == 0:
                studio_state.save()
                
        await process.wait()
        
        # 1. Immediately persist success or failed state so the user is unblocked!
        status_str = "success" if process.returncode == 0 else "failed"
        book_conf = studio_state.get_book_process(slug)
        studio_state.update_book_process(
            slug,
            status=status_str,
            threads=book_conf.get("threads", 4),
            translate=book_conf.get("translate", True),
            logs=list(process_logs[slug])
        )
        response_cache.clear(slug)
        logger.info(f"Process ended for {slug} with code {process.returncode}. Marked status as {status_str}.")
        
        # 2. Pack the book asynchronously in the background only when all pages are 100% complete!
        if process.returncode == 0:
            should_pack = False
            try:
                book = BookPaths.open(book_path)
                summary = book_status_summary(book)
                total_pages = summary.get("page_count", 0)
                required_languages = [book.default_lang()]
                if book_conf.get("translate", True):
                    other_lang = "en" if book.default_lang() == "vi" else "vi"
                    required_languages.append(other_lang)
                languages_complete = all(
                    sum(
                        1
                        for page in book.pages_dir(lang).glob("page_*.html")
                        if draft_html_file_valid(page)
                    ) == total_pages
                    for lang in required_languages
                )
                should_pack = (total_pages > 0) and languages_complete
            except Exception as se:
                logger.error(f"Error checking book completeness: {se}")
                should_pack = False

            if should_pack:
                async def background_pack():
                    try:
                        logger.info(f"Starting background packing for {slug}...")
                        bkb_dest = books_dir() / "bkbs" / f"{slug}.bkb"
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, pack_book, book_path, bkb_dest)
                        
                        # Update logs and save status with the pack notice
                        process_logs[slug].append(f"\n[SERVER] Automatically packed book to: books/bkbs/{slug}.bkb\n")
                        b_conf = studio_state.get_book_process(slug)
                        studio_state.update_book_process(
                            slug,
                            status="success",
                            threads=b_conf.get("threads", 4),
                            translate=b_conf.get("translate", True),
                            logs=list(process_logs[slug])
                        )
                        logger.info(f"Background packing complete for {slug}.")
                    except Exception as pe:
                        logger.error(f"Background auto-pack failed for {slug}: {pe}")
                        process_logs[slug].append(f"\n[SERVER ERROR] Failed to pack book: {pe}\n")
                        b_conf = studio_state.get_book_process(slug)
                        studio_state.update_book_process(
                            slug,
                            status="success",
                            threads=b_conf.get("threads", 4),
                            translate=b_conf.get("translate", True),
                            logs=list(process_logs[slug])
                        )
                
                asyncio.create_task(background_pack())
            else:
                logger.info(f"Skipping auto-pack for {slug} because the book is not 100% complete yet.")
                process_logs[slug].append(f"\n[SERVER] Skipped auto-pack (book is not 100% complete yet).\n")
                b_conf = studio_state.get_book_process(slug)
                studio_state.update_book_process(
                    slug,
                    status="success",
                    threads=b_conf.get("threads", 4),
                    translate=b_conf.get("translate", True),
                    logs=list(process_logs[slug])
                )
            
    except Exception as e:
        logger.error(f"Error reading process output: {e}")
        # Persist failure state
        book_conf = studio_state.get_book_process(slug)
        studio_state.update_book_process(
            slug,
            status="failed",
            threads=book_conf.get("threads", 4),
            translate=book_conf.get("translate", True),
            logs=process_logs.get(slug, [str(e)])
        )
    finally:
        running_processes.pop(slug, None)

async def start_book_processing_impl(
    slug: str,
    pages: Optional[str] = None,
    threads: int = 4,
    translate: bool = True,
    force: bool = False,
    custom_prompt: Optional[str] = None,
    log_prefix: str = "[SERVER]"
) -> bool:
    book_path = books_dir() / slug
    if not book_path.is_dir():
        return False
    # Vietnamese sources are always bilingual: render VI first, then create EN.
    if BookPaths.open(book_path).default_lang() == "vi":
        translate = True
        
    if slug in running_processes or slug in starting_processes:
        return False
    starting_processes.add(slug)

    py_bin = str(Path(repo_root()) / "application" / ".venv" / "bin" / "python3")
    if not Path(py_bin).is_file():
        py_bin = "python3"
        
    batch_script = str(Path(repo_root()) / "application" / "backend" / "scripts" / "batch_processor.py")
    
    cmd = [
        py_bin, "-u", batch_script,
        "--book", str(book_path),
        "--threads", str(threads),
        "--provider", "antigravity"
    ]
    if translate:
        cmd.append("--translate")
    if force:
        cmd.append("--force")
    if pages:
        cmd.extend(["--pages", pages])
    if custom_prompt:
        cmd.extend(["--custom-prompt", custom_prompt])

    logger.info(f"{log_prefix} Spawning batch processor: {' '.join(cmd)}")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(repo_root()) / "application" / "backend")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(repo_root()),
            env=env,
            start_new_session=True
        )
        
        studio_state.update_book_process(
            slug,
            status="running",
            threads=threads,
            translate=translate,
            logs=[f"{log_prefix} Started processing for '{slug}'...\n"]
        )
        
        running_processes[slug] = process
        process_logs[slug] = studio_state.data["books"][slug]["logs"]
        
        asyncio.create_task(read_subprocess_output(slug, process, book_path))
        response_cache.clear(slug)
        return True
    except Exception as e:
        logger.error(f"{log_prefix} Failed to start process: {e}")
        return False
    finally:
        starting_processes.discard(slug)

@app.post("/api/books/{slug}/process")
async def process_book(slug: str, config: ProcessConfig):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
        
    if slug in running_processes or slug in starting_processes:
        return {"success": False, "message": "Processor is already running for this book"}

    success = await start_book_processing_impl(
        slug,
        pages=config.pages,
        threads=config.threads,
        translate=config.translate,
        force=config.force,
        custom_prompt=config.custom_prompt,
        log_prefix="[SERVER]"
    )
    if success:
        return {"success": True, "message": "Processing started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start process")


@app.post("/api/books/{slug}/repair-page/{page}")
async def repair_failed_page(slug: str, page: int):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    if slug in running_processes or slug in starting_processes:
        return {"success": False, "message": "Processor is already running for this book"}

    report = read_repair_report(book_path)
    reported_pages = {
        int(item.get("page"))
        for item in (report or {}).get("pages", [])
        if isinstance(item, dict) and item.get("page") is not None
    }
    if page not in reported_pages:
        raise HTTPException(status_code=404, detail=f"Page {page} is not in the current repair report")

    book_conf = studio_state.get_book_process(slug)
    page_has_vi_issue = any(
        isinstance(issue, dict)
        and str(issue.get("page")) == str(page)
        and issue.get("lang") == "vi"
        for issue in (report or {}).get("issues", [])
    )
    success = await start_book_processing_impl(
        slug,
        pages=str(page),
        threads=1,
        translate=bool(book_conf.get("translate", True) or page_has_vi_issue),
        force=True,
        log_prefix="[Page Repair]",
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start page repair")
    return {"success": True, "page": page, "message": f"Repair started for page {page}"}


def _editor_book(slug: str) -> Path:
    if not _valid_preview_segment(slug):
        raise HTTPException(status_code=404, detail="Book not found")
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    return book_path


def _page_editor_book(slug: str, page: int) -> Path:
    if page < 1:
        raise HTTPException(status_code=404, detail="Page not found")
    return _editor_book(slug)


def _page_editor_lock_reason(slug: str) -> str | None:
    if slug in running_processes or slug in starting_processes:
        return "The page editor is read-only while the book pipeline is running"
    if slug in pdf_export_tasks:
        return "The page editor is read-only while PDF export is running"
    return None


@app.get("/api/books/{slug}/pages/{page}/source")
def get_page_source(slug: str, page: int, lang: str = "en"):
    book_path = _page_editor_book(slug, page)
    try:
        source = read_page_source(book_path, page, lang)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{lang.upper()} HTML for page {page} was not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    lock_reason = _page_editor_lock_reason(slug)
    return {**source, "locked": bool(lock_reason), "lock_reason": lock_reason}


@app.post("/api/books/{slug}/pages/{page}/validate")
def validate_page_html(slug: str, page: int, payload: PageEditorPayload):
    book_path = _page_editor_book(slug, page)
    try:
        return validate_page_source(book_path, page, payload.lang, payload.html)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/books/{slug}/pages/{page}/source")
def update_page_source(slug: str, page: int, payload: PageEditorPayload):
    book_path = _page_editor_book(slug, page)
    lock_reason = _page_editor_lock_reason(slug)
    if lock_reason:
        raise HTTPException(status_code=409, detail=lock_reason)
    if not payload.revision:
        raise HTTPException(status_code=400, detail="A source revision is required when saving")
    try:
        result = save_page_source(
            book_path,
            page,
            payload.lang,
            payload.html,
            expected_revision=payload.revision,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{payload.lang.upper()} HTML for page {page} was not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    response_cache.clear(slug)
    return {"success": True, **result}


@app.get("/api/books/{slug}/editor/stylesheets")
def get_editor_stylesheets(slug: str):
    book_path = _editor_book(slug)
    return {"stylesheets": list_stylesheet_sources(book_path)}


@app.get("/api/books/{slug}/editor/stylesheets/{filename}/source")
def get_stylesheet_source(slug: str, filename: str):
    book_path = _editor_book(slug)
    try:
        source = read_stylesheet_source(book_path, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Stylesheet {filename} was not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    lock_reason = _page_editor_lock_reason(slug)
    return {**source, "locked": bool(lock_reason), "lock_reason": lock_reason}


@app.post("/api/books/{slug}/editor/stylesheets/{filename}/validate")
def validate_stylesheet(slug: str, filename: str, payload: StylesheetEditorPayload):
    book_path = _editor_book(slug)
    try:
        path = read_stylesheet_source(book_path, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Stylesheet {filename} was not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not path:
        raise HTTPException(status_code=404, detail=f"Stylesheet {filename} was not found")
    return validate_stylesheet_source(payload.css)


@app.put("/api/books/{slug}/editor/stylesheets/{filename}/source")
def update_stylesheet_source(slug: str, filename: str, payload: StylesheetEditorPayload):
    book_path = _editor_book(slug)
    lock_reason = _page_editor_lock_reason(slug)
    if lock_reason:
        raise HTTPException(status_code=409, detail=lock_reason)
    if not payload.revision:
        raise HTTPException(status_code=400, detail="A source revision is required when saving")
    try:
        result = save_stylesheet_source(
            book_path,
            filename,
            payload.css,
            expected_revision=payload.revision,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Stylesheet {filename} was not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    response_cache.clear(slug)
    return {"success": True, **result}

@app.get("/api/books/{slug}/logs")
async def get_logs_stream(slug: str):
    async def log_generator():
        # Retrieve logs from memory or persistent history
        history = process_logs.get(slug)
        if history is None:
            book_conf = studio_state.get_book_process(slug)
            history = book_conf.get("logs", [])
            
        for line in history:
            yield f"data: {json.dumps({'log': line})}\n\n"
            
        last_index = len(history)
        while slug in running_processes:
            active_history = process_logs.get(slug, [])
            if len(active_history) > last_index:
                for line in active_history[last_index:]:
                    yield f"data: {json.dumps({'log': line})}\n\n"
                last_index = len(active_history)
            await asyncio.sleep(0.3)
            
        # Send remaining logs
        active_history = process_logs.get(slug, [])
        if len(active_history) > last_index:
            for line in active_history[last_index:]:
                yield f"data: {json.dumps({'log': line})}\n\n"

    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.get("/api/books/{slug}/pages/{page}/logs")
async def get_page_logs_stream(slug: str, page: int):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
        
    from books_core.paths import BookPaths
    book = BookPaths.open(book_path)
    
    from books_core.pipeline.status import live_log_path
    log_file = live_log_path(book, page)
    
    async def log_generator():
        # Send existing logs
        if log_file.is_file():
            try:
                content = log_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    yield f"data: {json.dumps({'log': line + '\n'})}\n\n"
            except Exception:
                pass
                
        last_size = log_file.stat().st_size if log_file.is_file() else 0
        
        while slug in running_processes:
            await asyncio.sleep(0.5)
            if log_file.is_file():
                current_size = log_file.stat().st_size
                if current_size > last_size:
                    try:
                        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_size)
                            new_data = f.read()
                            for line in new_data.splitlines():
                                yield f"data: {json.dumps({'log': line + '\n'})}\n\n"
                        last_size = current_size
                    except Exception:
                        pass
                        
        if log_file.is_file():
            current_size = log_file.stat().st_size
            if current_size > last_size:
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        new_data = f.read()
                        for line in new_data.splitlines():
                            yield f"data: {json.dumps({'log': line + '\n'})}\n\n"
                except Exception:
                    pass

    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.post("/api/books/{slug}/stop")
def stop_book_processing(slug: str):
    process = running_processes.get(slug)
    if not process:
        return {"success": False, "message": "No active process running"}
    try:
        import os, signal
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            process.terminate()
        response_cache.clear(slug)
        return {"success": True, "message": "Terminate signal sent to batch processor"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/books/{slug}/pack")
def pack_book_endpoint(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        book = BookPaths.open(book_path)
        # Assemble EN and VI before packing to make sure they are up-to-date
        try:
            from books_core.assemble import assemble_book_html
            assemble_book_html(book, "en")
            if (book.pages_dir("vi")).is_dir():
                assemble_book_html(book, "vi")
        except Exception as ae:
            logger.warning(f"Pre-pack assembly warning: {ae}")
            
        bkb_dest = books_dir() / "bkbs" / f"{slug}.bkb"
        result = pack_book(book_path, bkb_dest)
        response_cache.clear(slug)
        return {"success": True, "archive": result["archive"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _run_pdf_export(slug: str, book_path: Path) -> None:
    from books_core.assemble import assemble_book_html
    from books_core.pdf_export import export_html_pdf

    status = pdf_export_status[slug]
    generated: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    try:
        book = BookPaths.open(book_path)
        expected_pages = book.estimate_page_count()
        for lang, html_name, pdf_name in (
            ("en", "book.html", "book.pdf"),
            ("vi", "book.vi.html", "book.vi.pdf"),
        ):
            pages = sorted(book.pages_dir(lang).glob("page_*.html")) if book.pages_dir(lang).is_dir() else []
            if not pages:
                skipped[lang] = "No rendered HTML pages"
                continue
            if expected_pages and len(pages) != expected_pages:
                skipped[lang] = f"Expected {expected_pages} pages, found {len(pages)}"
                continue
            invalid_pages = [
                int(path.stem.split("_")[1])
                for path in pages
                if not draft_html_file_valid(path)
            ]
            if invalid_pages:
                skipped[lang] = (
                    f"{len(invalid_pages)} blank/invalid page(s): {invalid_pages[:10]}"
                )
                continue
            status.update({"state": "running", "language": lang, "message": f"Exporting {lang.upper()} PDF..."})
            response_cache.clear(slug)
            assemble_book_html(book, lang, html_name)
            generated[lang] = await export_html_pdf(
                book.output_dir / html_name,
                book.output_dir / pdf_name,
            )

        if not generated:
            details = "; ".join(f"{lang.upper()}: {reason}" for lang, reason in skipped.items())
            raise RuntimeError(f"No complete language is ready for PDF export. {details}")
        state = "success" if not skipped else "partial"
        message = f"Generated {', '.join(lang.upper() for lang in generated)} PDF"
        if skipped:
            message += "; skipped " + ", ".join(lang.upper() for lang in skipped)
        status.update(
            {
                "state": state,
                "language": None,
                "message": message,
                "generated": generated,
                "skipped": skipped,
                "error": None,
            }
        )
    except Exception as exc:
        logger.exception("PDF export failed for %s", slug)
        status.update(
            {
                "state": "failed",
                "language": None,
                "message": "PDF export failed",
                "generated": generated,
                "skipped": skipped,
                "error": str(exc),
            }
        )
    finally:
        pdf_export_tasks.pop(slug, None)
        response_cache.clear(slug)


@app.post("/api/books/{slug}/export-pdf")
async def export_book_pdf_endpoint(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    if slug in running_processes or slug in starting_processes:
        return {"success": False, "message": "Wait for page processing to finish before exporting PDF"}
    if slug in pdf_export_tasks:
        return {"success": False, "message": "PDF export is already running"}

    pdf_export_status[slug] = {
        "state": "running",
        "language": None,
        "message": "Preparing assembled HTML...",
        "generated": {},
        "skipped": {},
        "error": None,
    }
    task = asyncio.create_task(_run_pdf_export(slug, book_path))
    pdf_export_tasks[slug] = task
    response_cache.clear(slug)
    return {"success": True, "message": "PDF export started"}


@app.get("/api/books/{slug}/download-pdf/{lang}")
def download_book_pdf(slug: str, lang: str):
    if lang not in {"en", "vi"}:
        raise HTTPException(status_code=400, detail="Language must be 'en' or 'vi'")
    book_path = books_dir() / slug
    pdf_name = "book.pdf" if lang == "en" else "book.vi.pdf"
    pdf_path = book_path / "output" / pdf_name
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"{lang.upper()} PDF has not been generated")
    return FileResponse(
        path=str(pdf_path),
        filename=f"{slug}.{lang}.pdf",
        media_type="application/pdf",
    )

@app.post("/api/books/{slug}/verify")
async def verify_book_endpoint(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        from books_core.book_layout import verify_book
        result = verify_book(book_path, force_assets=True)
        
        broken = result.get("broken_pages", [])
        auto_repair_started = False
        if broken:
            pages_str = ",".join(str(p) for p in broken)
            book_conf = studio_state.get_book_process(slug)
            threads = book_conf.get("threads", 4)
            translate = book_conf.get("translate", True)
            
            auto_repair_started = await start_book_processing_impl(
                slug,
                pages=pages_str,
                threads=threads,
                translate=translate,
                force=True,
                log_prefix="[Auto-Repair]"
            )
            if auto_repair_started:
                result["warnings"].append(f"[Auto-Repair] Automatically spawned agents to repair {len(broken)} pages: {pages_str}")
        
        result["auto_repair_started"] = auto_repair_started
        response_cache.clear(slug)
        return result
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{slug}/download")
def download_packed_book(slug: str):
    bkb_path1 = books_dir() / f"{slug}.bkb"
    bkb_path2 = books_dir() / "bkbs" / f"{slug}.bkb"
    
    target_path = bkb_path2 if bkb_path2.is_file() else bkb_path1
    if not target_path.is_file():
        # Try to pack on the fly if the book folder exists and has output
        book_path = books_dir() / slug
        if book_path.is_dir() and (book_path / "output").is_dir():
            try:
                book = BookPaths.open(book_path)
                try:
                    from books_core.assemble import assemble_book_html
                    assemble_book_html(book, "en")
                    if (book.pages_dir("vi")).is_dir():
                        assemble_book_html(book, "vi")
                except Exception as ae:
                    logger.warning(f"On-the-fly pre-pack assembly warning: {ae}")
                
                bkb_dest = books_dir() / "bkbs" / f"{slug}.bkb"
                pack_book(book_path, bkb_dest)
                target_path = bkb_dest
            except Exception as e:
                logger.error(f"On-the-fly packing failed: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to generate packed book on the fly: {str(e)}")
        else:
            raise HTTPException(status_code=404, detail="Packed book (.bkb) file not found. Please process the book first.")
        
    return FileResponse(
        path=str(target_path),
        filename=f"{slug}.bkb",
        media_type="application/octet-stream"
    )

class UpdateBookRequest(BaseModel):
    title: str

@app.patch("/api/books/{slug}")
def update_book(slug: str, req: UpdateBookRequest):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        book = BookPaths.open(book_path)
        book_data = book.load_book_json()
        book_data["title"] = req.title
        book.book_json.write_text(json.dumps(book_data, indent=2, ensure_ascii=False), encoding="utf-8")
        response_cache.clear(slug)
        return {"success": True, "title": req.title}
    except Exception as e:
        logger.error(f"Failed to update book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/books/{slug}")
def delete_book(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    if slug in running_processes:
        raise HTTPException(status_code=400, detail="Cannot delete book while processing is running")
    try:
        shutil.rmtree(book_path)
        
        # Clean up any packed bilingual book (.bkb) files
        bkb_file1 = books_dir() / f"{slug}.bkb"
        if bkb_file1.is_file():
            bkb_file1.unlink()
            
        bkb_file2 = books_dir() / "bkbs" / f"{slug}.bkb"
        if bkb_file2.is_file():
            bkb_file2.unlink()

        studio_state.remove_book(slug)
        response_cache.clear(slug)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Serve SPA index
@app.get("/", response_class=HTMLResponse)
def get_index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.is_file():
        return template_path.read_text(encoding="utf-8")
    return HTMLResponse("<h3>Template index.html not found! Please create it.</h3>", status_code=404)
