"""Clinic queue demo: QR walk-in, live status link, WhatsApp token.
Run:  uvicorn main:app --reload      (see README.md for settings)"""
import os, io, time, hmac, hashlib, sqlite3, secrets, html, datetime
from contextlib import closing
import httpx, segno
from pathlib import Path
from fastapi import FastAPI, Form, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---- settings (override with environment variables) ----
STAFF_PIN = os.getenv("STAFF_PIN", "1234")
SECRET = os.getenv("APP_SECRET", "change-me")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
CLINIC = os.getenv("CLINIC_NAME", "SmartClinic Demo")
DOCTORS = [d.strip() for d in os.getenv("DOCTORS", "Dr. Sharma,Dr. Rao").split(",") if d.strip()]
DB = os.getenv("DB_PATH", "queue.db")
WA_TOKEN = os.getenv("WA_TOKEN")              # Meta permanent/temporary access token
WA_PHONE_ID = os.getenv("WA_PHONE_ID")        # WhatsApp phone number ID
WA_TEMPLATE = os.getenv("WA_TEMPLATE", "queue_token")
WA_LANG = os.getenv("WA_LANG", "en")
WA_VERSION = os.getenv("WA_API_VERSION", "v21.0")   # check Meta docs for the current version
TAGLINE = os.getenv("TAGLINE", "Patient queue")
CENTER_PHONE = os.getenv("CENTER_PHONE", "")
CENTER_ADDRESS = os.getenv("CENTER_ADDRESS", "")
DEFAULT_MIN = 8   # minutes per patient until real data exists

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Clinic Queue Demo")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals.update(clinic=CLINIC, tagline=TAGLINE, phone=CENTER_PHONE, address=CENTER_ADDRESS)

def mmss(sec):
    """Seconds -> 07:45 (or 1:07:45), used for the running clocks."""
    sec = max(0, int(sec)); h, rem = divmod(sec, 3600); m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

templates.env.filters["mmss"] = mmss

def render(request, template, status=200, **ctx):
    """Render templates/<template> with the given values."""
    return templates.TemplateResponse(request, template, ctx, status_code=status)
if STAFF_PIN == "1234" or SECRET == "change-me":
    print("WARNING: set STAFF_PIN and APP_SECRET before using this outside your laptop.")

# ---- database ----
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with closing(db()) as _c:
    _c.execute("""CREATE TABLE IF NOT EXISTS tokens(
        id TEXT PRIMARY KEY, day TEXT, no INTEGER, doctor TEXT, name TEXT, phone TEXT,
        status TEXT, created REAL, called REAL, finished REAL)""")
    _c.commit()

def today():  # clinic day in IST, so numbering restarts at local midnight
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).date().isoformat()

def avg_min(c, doctor):
    rows = c.execute("""SELECT called, finished FROM tokens WHERE doctor=? AND status='done'
        AND called IS NOT NULL AND finished IS NOT NULL ORDER BY finished DESC LIMIT 10""", (doctor,)).fetchall()
    mins = [(r["finished"] - r["called"]) / 60 for r in rows]
    mins = [m for m in mins if 0.5 <= m <= 60]       # ignore accidental clicks
    return sum(mins) / len(mins) if mins else DEFAULT_MIN

# ---- WhatsApp ----
def send_token(phone, no, doctor, link):
    msg = f"{CLINIC}: your token is {no} for {doctor}. Track your queue: {link}"
    if not (WA_TOKEN and WA_PHONE_ID):
        print(f"[WhatsApp DEMO MODE -> {phone}] {msg}")
        return
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "template",
               "template": {"name": WA_TEMPLATE, "language": {"code": WA_LANG},
                            "components": [{"type": "body", "parameters": [
                                {"type": "text", "text": str(no)},
                                {"type": "text", "text": doctor},
                                {"type": "text", "text": link}]}]}}
    try:
        r = httpx.post(f"https://graph.facebook.com/{WA_VERSION}/{WA_PHONE_ID}/messages",
                       json=payload, headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=15)
        print("[WhatsApp]", r.status_code, r.text[:300])
    except Exception as e:
        print("[WhatsApp error]", e)

# ---- patient routes ----
@app.get("/")
def home():
    return RedirectResponse("/join")

@app.get("/join")
def join_get(request: Request):
    return render(request, "join.html", doctors=DOCTORS, error="", f_name="", f_phone="", f_doctor="")

@app.post("/join")
def join_post(request: Request, bg: BackgroundTasks, name: str = Form(...), phone: str = Form(...), doctor: str = Form(...)):
    name = " ".join(name.split())[:60]
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    error = ""
    if len(name) < 2:
        error = "Please enter your name."
    elif len(digits) != 10:
        error = "Enter a valid 10-digit mobile number."
    elif doctor not in DOCTORS:
        error = "Please choose from the list."
    if error:
        return render(request, "join.html", 400, doctors=DOCTORS, error=error, f_name=name, f_phone=phone, f_doctor=doctor)
    pid = secrets.token_urlsafe(8)
    with closing(db()) as c:
        no = c.execute("SELECT COALESCE(MAX(no),0)+1 n FROM tokens WHERE day=?", (today(),)).fetchone()["n"]
        c.execute("INSERT INTO tokens VALUES(?,?,?,?,?,?,?,?,NULL,NULL)",
                  (pid, today(), no, doctor, name, "91" + digits, "waiting", time.time()))
        c.commit()
    bg.add_task(send_token, "91" + digits, no, doctor, f"{BASE_URL}/s/{pid}")
    return RedirectResponse(f"/s/{pid}", 303)

def status_of(pid):
    with closing(db()) as c:
        me = c.execute("SELECT * FROM tokens WHERE id=?", (pid,)).fetchone()
        if not me:
            return None
        day, doc = me["day"], me["doctor"]
        ahead = c.execute("SELECT COUNT(*) n FROM tokens WHERE day=? AND doctor=? AND status='waiting' AND no<?",
                          (day, doc, me["no"])).fetchone()["n"]
        cur = c.execute("SELECT no FROM tokens WHERE day=? AND doctor=? AND status='called' ORDER BY no DESC LIMIT 1",
                        (day, doc)).fetchone()
        avg = avg_min(c, doc)
    wait = ahead * avg + (avg / 2 if cur else 0)
    st = "expired" if day != today() and me["status"] in ("waiting", "called") else me["status"]
    now = time.time()
    if st == "waiting":
        el, label, run = now - me["created"], "Waiting time", True
    elif st == "called":
        el, label, run = now - (me["called"] or now), "In consultation", True
    elif st == "done":
        el, label, run = (me["finished"] or now) - me["created"], "Total time", False
    else:
        el, label, run = 0, "", False
    return {"token": me["no"], "doctor": doc, "status": st, "serving": cur["no"] if cur else None,
            "ahead": ahead, "wait_min": max(1, round(wait)) if st == "waiting" else 0,
            "elapsed_sec": int(el), "timer_label": label, "running": run}

@app.get("/api/status/{pid}")
def api_status(pid: str):
    s = status_of(pid)
    return JSONResponse(s, headers={"Cache-Control": "no-store"}) if s else JSONResponse({"error": "not found"}, 404)

@app.get("/s/{pid}")
def status_page(request: Request, pid: str):
    return render(request, "status.html")

# ---- QR + printable poster ----
@app.get("/qr.svg")
def qr():
    buf = io.BytesIO()
    segno.make(f"{BASE_URL}/join", error="m").save(buf, kind="svg", scale=10, border=2, dark="#12303b")
    return Response(buf.getvalue(), media_type="image/svg+xml")

@app.get("/poster")
def poster(request: Request):
    return render(request, "poster.html")

# ---- staff ----
def sig():
    return hmac.new(SECRET.encode(), b"staff:" + STAFF_PIN.encode(), hashlib.sha256).hexdigest()

def authed(request: Request):
    return hmac.compare_digest(request.cookies.get("staff", "").encode(), sig().encode())
from analytics import create_analytics_router

app.include_router(create_analytics_router(db, authed))

@app.post("/staff/login")
def staff_login(request: Request, pin: str = Form(...)):
    if not hmac.compare_digest(pin.encode(), STAFF_PIN.encode()):
        return render(request, "login.html", 401, error="Wrong PIN. Try again.")
    r = RedirectResponse("/staff", 303)
    r.set_cookie("staff", sig(), httponly=True, samesite="lax", max_age=12 * 3600, secure=BASE_URL.startswith("https"))
    return r

@app.get("/staff/logout")
def staff_logout():
    r = RedirectResponse("/staff", 303)
    r.delete_cookie("staff")
    return r

@app.get("/staff")
def staff(request: Request, doc: int = 0):
    if not authed(request):
        return render(request, "login.html", error="")
    doc = doc if 0 <= doc < len(DOCTORS) else 0
    d = DOCTORS[doc]
    with closing(db()) as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM tokens WHERE day=? AND doctor=? ORDER BY no", (today(), d))]
        avg = avg_min(c, d)
    now = time.time()
    for r in rows:
        r["wait_sec"] = int(now - r["created"])
        r["sec"] = int(now - r["called"]) if r["called"] else 0
    cur = [r for r in rows if r["status"] == "called"]
    waiting = [r for r in rows if r["status"] == "waiting"]
    return render(request, "staff.html", doctors=DOCTORS, doc=doc, avg=round(avg),
                  current=cur[0] if cur else None, waiting=waiting,
                  longest=max((r["wait_sec"] for r in waiting), default=0),
                  skipped=[r for r in rows if r["status"] == "skipped"],
                  done=sum(1 for r in rows if r["status"] == "done"))

@app.post("/staff/action")
def staff_action(request: Request, action: str = Form(...), doc: int = Form(0), id: str = Form("")):
    if not authed(request):
        return RedirectResponse("/staff", 303)
    doc = doc if 0 <= doc < len(DOCTORS) else 0
    d, now, day = DOCTORS[doc], time.time(), today()
    with closing(db()) as c:
        if action in ("call_next", "done"):
            c.execute("UPDATE tokens SET status='done', finished=? WHERE day=? AND doctor=? AND status='called'", (now, day, d))
        if action == "call_next":
            nxt = c.execute("SELECT id FROM tokens WHERE day=? AND doctor=? AND status='waiting' ORDER BY no LIMIT 1", (day, d)).fetchone()
            if nxt:
                c.execute("UPDATE tokens SET status='called', called=? WHERE id=?", (now, nxt["id"]))
        elif action == "skip":
            c.execute("UPDATE tokens SET status='skipped' WHERE id=? AND status='waiting'", (id,))
        elif action == "restore":
            c.execute("UPDATE tokens SET status='waiting' WHERE id=? AND status='skipped'", (id,))
        c.commit()
    return RedirectResponse(f"/staff?doc={doc}", 303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
