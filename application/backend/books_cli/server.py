import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from books_core.repo import default_library_root, books_dir, repo_root
from books_core.ingest import ingest_pdf
from books_core.paths import BookPaths
from books_core.meta.reader import book_status_summary
from books_core.package import pack_book

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("books_server")

app = FastAPI(title="Bilingual Reader Book Studio")
app.mount("/books", StaticFiles(directory=str(books_dir())), name="books")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

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

# Cache for active tasks and logs
# slug -> asyncio.subprocess.Process
running_processes: Dict[str, asyncio.subprocess.Process] = {}
# slug -> list of string logs
process_logs: Dict[str, List[str]] = {}

class LoginSession:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.oauth_url: Optional[str] = None
        self.logs: List[str] = []
        self.status: str = "idle"  # idle, starting, waiting_code, verifying, success, failed

# Singleton login session
login_session = LoginSession()

def get_agy_binary() -> str:
    for path in ["/Users/thaonv/.local/bin/agy", "agy"]:
        if shutil.which(path):
            return path
    return "agy"

def get_token_path() -> Path:
    return Path.home() / ".gemini/antigravity-cli/antigravity-oauth-token"

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

    def get_book_process(self, slug: str) -> dict:
        return self.data["books"].get(slug, {
            "status": "idle",
            "threads": 4,
            "translate": True,
            "logs": [],
            "last_processed": 0.0
        })

# Instantiate singleton persistent state
studio_state = StudioState()

def find_logged_in_email() -> Optional[str]:
    # 1. Try to find the email in the most recent agy CLI log files
    log_dir = Path.home() / ".gemini/antigravity-cli/log"
    if log_dir.is_dir():
        log_files = sorted(log_dir.glob("cli-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        email_pattern = re.compile(r"authenticated successfully as ([a-zA-Z0-9\.\-\_\+]+@[a-zA-Z0-9\.\-]+)")
        email_pattern_alt = re.compile(r"email=([a-zA-Z0-9\.\-\_\+]+@[a-zA-Z0-9\.\-]+)")
        
        for log_file in log_files[:10]:
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    m = email_pattern.search(line)
                    if m:
                        return m.group(1)
                    m = email_pattern_alt.search(line)
                    if m:
                        return m.group(1)
            except Exception:
                continue
    return None

_auth_cache = {"logged_in": False, "last_check": 0.0}

def is_agy_authenticated(force: bool = False) -> bool:
    now = time.time()
    # Cache auth status for 60 seconds unless forced
    if not force and (now - _auth_cache["last_check"] < 60.0):
        return _auth_cache["logged_in"]
        
    # First, quick local check for token file
    token_file = get_token_path()
    if token_file.is_file() and token_file.stat().st_size > 0:
        _auth_cache["logged_in"] = True
        _auth_cache["last_check"] = now
        email = find_logged_in_email()
        studio_state.update_auth(logged_in=True, email=email)
        return True
        
    # Second, check OS Keychain / secure keyring by executing a fast, non-interactive command
    agy_bin = get_agy_binary()
    try:
        proc = subprocess.run(
            [agy_bin, "models"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        is_auth = (proc.returncode == 0) and any(m in proc.stdout for m in ["Gemini", "Claude", "GPT"])
        _auth_cache["logged_in"] = is_auth
    except Exception:
        _auth_cache["logged_in"] = False
        
    _auth_cache["last_check"] = now
    
    if _auth_cache["logged_in"]:
        email = find_logged_in_email()
        studio_state.update_auth(logged_in=True, email=email)
    else:
        studio_state.update_auth(logged_in=False)
        
    return _auth_cache["logged_in"]

@app.get("/api/auth/status")
def get_auth_status(force: bool = False):
    logged_in = is_agy_authenticated(force=force)
    return {
        "logged_in": logged_in,
        "email": studio_state.data["auth"].get("email"),
        "status": login_session.status,
        "oauth_url": login_session.oauth_url
    }
@app.get("/api/auth/quota")
def get_auth_quota():
    if not is_agy_authenticated(force=False):
        return {"success": False, "error": "Not authenticated"}
    
    agy_bin = get_agy_binary()
    try:
        import os
        script_path = os.path.join(os.path.dirname(__file__), "fetch_quota_tmux.sh")
        proc = subprocess.run(
            [script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if proc.returncode != 0:
            return {"success": False, "error": "Failed to retrieve quota"}
            
        output = proc.stdout
        
        # Clean ANSI codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output = ansi_escape.sub('', output)
        
        quota = {"account": "", "groups": []}
        
        acc_match = re.search(r'Account:\s*([^\n]+)', output)
        if acc_match:
            quota["account"] = acc_match.group(1).strip()
            
        lines = output.split('\n')
        current_group = None
        current_limit = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Group (e.g. GEMINI MODELS)
            if re.match(r'^[A-Z0-9\s]+$', line.strip()) and len(line.strip()) > 0 and i + 1 < len(lines) and "Models within this group:" in lines[i+1]:
                if current_group:
                    if current_limit:
                        current_group["limits"].append(current_limit)
                        current_limit = None
                    quota["groups"].append(current_group)
                
                group_name = line.strip()
                models_str = lines[i+1].split("Models within this group:")[1].strip()
                current_group = {"name": group_name, "models": models_str, "limits": []}
                i += 2
                continue
                
            # Limit (e.g. Weekly Limit)
            if current_group and re.match(r'^[A-Za-z\s]+Limit$', line.strip()):
                if current_limit:
                    current_group["limits"].append(current_limit)
                
                limit_name = line.strip()
                if i + 1 < len(lines) and "[" in lines[i+1] and "%" in lines[i+1]:
                    pct_match = re.search(r'([0-9\.]+)\%', lines[i+1])
                    pct = float(pct_match.group(1)) if pct_match else 0.0
                    used = round(100.0 - pct, 2)
                    
                    desc = lines[i+2].strip() if i + 2 < len(lines) else ""
                    
                    color = "#22c55e" # Green
                    if used > 90:
                        color = "#ef4444" # Red
                    elif used > 75:
                        color = "#f59e0b" # Orange
                        
                    current_limit = {
                        "name": limit_name,
                        "percent": used,
                        "color": color,
                        "info": desc
                    }
                    i += 3
                    continue
            
            i += 1
            
        if current_group:
            if current_limit:
                current_group["limits"].append(current_limit)
            quota["groups"].append(current_group)
            
        if not quota["account"] and not quota["groups"]:
            if "Eligibility check failed" in output:
                return {"success": False, "error": "Eligibility check failed. Re-authenticate AGY CLI."}
            elif "trust" in output.lower():
                return {"success": False, "error": "AGY CLI is blocked by a workspace trust prompt."}
            else:
                return {"success": False, "error": "Failed to parse quota from CLI."}

        return {"success": True, "quota": quota}
    except Exception as e:
        return {"success": False, "error": f"Error parsing quota: {str(e)}"}
@app.post("/api/auth/logout_agy")
def logout_agy_cli():
    try:
        # Run expect script to automate agy /logout
        script_path = Path(repo_root()) / "logout_agy.exp"
        if script_path.exists():
            subprocess.run(["expect", str(script_path)], timeout=10)
        
        token_file = get_token_path()
        if token_file.exists():
            token_file.unlink()
        _auth_cache["logged_in"] = False
        _auth_cache["last_check"] = 0
        studio_state.update_auth(logged_in=False, email=None)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/auth/login")
async def start_auth_login():
    global login_session
    
    # Terminate any existing login process
    if login_session.process and login_session.process.returncode is None:
        try:
            login_session.process.kill()
            await login_session.process.wait()
        except Exception:
            pass
            
    login_session = LoginSession()
    login_session.status = "starting"
    
    agy_bin = get_agy_binary()
    logger.info(f"Spawning '{agy_bin} login' to fetch OAuth link")
    
    try:
        script_path = Path(repo_root()) / "login_agy.exp"
        proc = await asyncio.create_subprocess_exec(
            "expect", str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        login_session.process = proc
    except Exception as e:
        login_session.status = "failed"
        logger.error(f"Failed to start agy login process: {e}")
        return {"success": False, "error": f"Failed to start agy login: {str(e)}"}

    # Scrape stdout to extract OAuth URL
    url_found = False
    for _ in range(30):  # read up to 30 lines
        if proc.returncode is not None:
            break
        try:
            line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8', errors='replace')
            login_session.logs.append(line)
            logger.info(f"agy-login stdout: {line.strip()}")
            
            # Check for URL patterns
            if "URL_FOUND_HERE:" in line:
                login_session.oauth_url = line.split("URL_FOUND_HERE:")[1].strip()
                login_session.status = "waiting_code"
                url_found = True
                break
        except asyncio.TimeoutError:
            continue
            
    if url_found:
        return {"success": True, "url": login_session.oauth_url}
    else:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        login_session.status = "failed"
        return {
            "success": False, 
            "error": "Could not find OAuth URL in CLI output.", 
            "logs": "".join(login_session.logs)
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
        
    # Read remaining stdout
    try:
        while True:
            line_bytes = await asyncio.wait_for(login_session.process.stdout.readline(), timeout=3.0)
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8', errors='replace')
            login_session.logs.append(line)
            logger.info(f"agy-login post-verify: {line.strip()}")
    except asyncio.TimeoutError:
        pass
        
    try:
        exit_code = await asyncio.wait_for(login_session.process.wait(), timeout=8.0)
    except asyncio.TimeoutError:
        try:
            login_session.process.kill()
            await login_session.process.wait()
        except Exception:
            pass
        exit_code = -1
        
    token_file = get_token_path()
    if exit_code == 0 or (token_file.is_file() and token_file.stat().st_size > 0) or is_agy_authenticated(force=True):
        login_session.status = "success"
        _auth_cache["logged_in"] = True
        _auth_cache["last_check"] = time.time()
        return {"success": True}
    else:
        login_session.status = "failed"
        return {
            "success": False, 
            "error": f"Verification exited with code {exit_code}", 
            "logs": "".join(login_session.logs)
        }

@app.get("/api/books")
def list_books_endpoint():
    books_folder = books_dir()
    found = []
    if books_folder.is_dir():
        for child in sorted(books_folder.iterdir()):
            if child.name.startswith("_") or child.name == "library.json":
                continue
            if child.is_dir() and BookPaths.open(child).source_pdf.is_file():
                try:
                    summary = book_status_summary(BookPaths.open(child))
                    
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
                        "status": persisted_status
                    })
                except Exception as e:
                    logger.warning(f"Error scanning book '{child.name}': {e}")
                    pass
    return {"books": found}

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    inbox = default_library_root() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    temp_path = inbox / file.filename
    
    logger.info(f"Saving uploaded file to {temp_path}")
    with open(temp_path, "wb") as f:
        f.write(await file.read())
        
    try:
        result = ingest_pdf(temp_path)
        return {"success": True, "book": result}
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{slug}/status")
def get_book_status_endpoint(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
        
    book = BookPaths.open(book_path)
    summary = book_status_summary(book)
    
    # Add translation status to pages
    pages_enriched = []
    for p in summary.get("pages", []):
        page_num = p["page"]
        vi_html = book.page_lang_html(page_num, "vi")
        p["translated"] = vi_html.is_file() and vi_html.stat().st_size > 0
        
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
    summary["running"] = slug in running_processes
    
    bkb_path1 = books_dir() / f"{slug}.bkb"
    bkb_path2 = books_dir() / "bkbs" / f"{slug}.bkb"
    summary["has_bkb"] = bkb_path1.is_file() or bkb_path2.is_file()
    
    # Check if assembled book files exist
    summary["has_book_html"] = (book.output_dir / "book.html").is_file()
    summary["has_book_vi_html"] = (book.output_dir / "book.vi.html").is_file()
    
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
        logger.info(f"Process ended for {slug} with code {process.returncode}. Marked status as {status_str}.")
        
        # 2. Pack the book asynchronously in the background only when all pages are 100% complete!
        if process.returncode == 0:
            should_pack = False
            try:
                summary = book_status_summary(BookPaths.open(book_path))
                total_pages = summary.get("page_count", 0)
                published_pages = summary.get("published", 0)
                
                # Check VI translations count if translate was requested
                vi_complete = True
                if book_conf.get("translate", True):
                    vi_dir = book_path / "output" / "vi"
                    vi_pages = sum(1 for p in vi_dir.glob("page_*.html") if p.is_file() and p.stat().st_size > 0) if vi_dir.is_dir() else 0
                    vi_complete = (vi_pages == total_pages)
                
                should_pack = (total_pages > 0) and (published_pages == total_pages) and vi_complete
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

@app.post("/api/books/{slug}/process")
async def process_book(slug: str, config: ProcessConfig):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
        
    if slug in running_processes:
        return {"success": False, "message": "Processor is already running for this book"}

    py_bin = str(Path(repo_root()) / "application" / ".venv" / "bin" / "python3")
    if not Path(py_bin).is_file():
        py_bin = "python3"
        
    batch_script = str(Path(repo_root()) / "application" / "backend" / "scripts" / "batch_processor.py")
    
    cmd = [
        py_bin, "-u", batch_script,
        "--book", str(book_path),
        "--threads", str(config.threads),
        "--provider", "antigravity"  # Lock provider to antigravity (agy)
    ]
    if config.translate:
        cmd.append("--translate")
    if config.force:
        cmd.append("--force")
    if config.pages:
        cmd.extend(["--pages", config.pages])

    logger.info(f"Spawning batch processor: {' '.join(cmd)}")
    
    # Copy the parent environment to preserve PATH, HOME, and other variables (like ANTIGRAVITY_MODEL)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(repo_root()) / "application" / "backend")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(repo_root()),
            env=env
        )
        
        # Persist initial status and logs in JSON state database
        studio_state.update_book_process(
            slug,
            status="running",
            threads=config.threads,
            translate=config.translate,
            logs=[f"[SERVER] Started processing for '{slug}'...\n"]
        )
        
        running_processes[slug] = process
        process_logs[slug] = studio_state.data["books"][slug]["logs"]
        
        asyncio.create_task(read_subprocess_output(slug, process, book_path))
        
        return {"success": True, "message": "Processing started"}
    except Exception as e:
        logger.error(f"Failed to start process: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        process.terminate()
        return {"success": True, "message": "Terminate signal sent to batch processor"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/books/{slug}/pack")
def pack_book_endpoint(slug: str):
    book_path = books_dir() / slug
    if not book_path.is_dir():
        raise HTTPException(status_code=404, detail="Book not found")
    try:
        bkb_dest = books_dir() / "bkbs" / f"{slug}.bkb"
        result = pack_book(book_path, bkb_dest)
        return {"success": True, "archive": result["archive"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{slug}/download")
def download_packed_book(slug: str):
    bkb_path1 = books_dir() / f"{slug}.bkb"
    bkb_path2 = books_dir() / "bkbs" / f"{slug}.bkb"
    
    target_path = bkb_path2 if bkb_path2.is_file() else bkb_path1
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Packed book (.bkb) file not found. Please run pack or process the book first.")
        
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
