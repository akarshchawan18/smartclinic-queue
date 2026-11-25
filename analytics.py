"""
SmartClinic Queue analytics add-on.
Copy beside main.py; include with:
from analytics import create_analytics_router
app.include_router(create_analytics_router(db, authed))
"""
from contextlib import closing
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

def create_analytics_router(db_factory, auth_checker):
    router = APIRouter()
    template_path = Path(__file__).resolve().parent / "templates" / "analytics.html"

    def allowed(request):
        return auth_checker(request)

    @router.get("/analytics", response_class=HTMLResponse)
    def analytics_page(request: Request):
        if not allowed(request):
            return RedirectResponse("/staff", status_code=303)
        if not template_path.exists():
            return HTMLResponse("Missing templates/analytics.html", status_code=500)
        return HTMLResponse(template_path.read_text(encoding="utf-8"))

    @router.get("/analytics/api/overview")
    def overview(request: Request, year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100)):
        if not allowed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        months = [f"{year}-{m:02d}" for m in range(1, 13)]
        with closing(db_factory()) as c:
            total = c.execute("SELECT COUNT(*) FROM tokens WHERE substr(day,1,4)=?", (str(year),)).fetchone()[0]
            unique = c.execute("SELECT COUNT(DISTINCT phone) FROM tokens WHERE substr(day,1,4)=?", (str(year),)).fetchone()[0]
            repeat = c.execute("""
                WITH first_visit AS (SELECT phone, MIN(created) first_created FROM tokens GROUP BY phone)
                SELECT COUNT(*) FROM tokens t JOIN first_visit f ON f.phone=t.phone
                WHERE substr(t.day,1,4)=? AND t.created>f.first_created
            """, (str(year),)).fetchone()[0]
            statuses = c.execute("SELECT status,COUNT(*) n FROM tokens WHERE substr(day,1,4)=? GROUP BY status", (str(year),)).fetchall()
            rows = c.execute("""
                WITH first_visit AS (SELECT phone,MIN(created) first_created FROM tokens GROUP BY phone)
                SELECT substr(t.day,1,7) month, COUNT(*) visits, COUNT(DISTINCT t.phone) unique_patients,
                SUM(CASE WHEN t.created=f.first_created THEN 1 ELSE 0 END) new_visits,
                SUM(CASE WHEN t.created>f.first_created THEN 1 ELSE 0 END) repeat_visits
                FROM tokens t JOIN first_visit f ON f.phone=t.phone
                WHERE substr(t.day,1,4)=? GROUP BY substr(t.day,1,7)
            """, (str(year),)).fetchall()
        by_month = {r["month"]: dict(r) for r in rows}
        monthly = [{"month": m, "visits": by_month.get(m, {}).get("visits", 0),
                    "unique_patients": by_month.get(m, {}).get("unique_patients", 0),
                    "new_visits": by_month.get(m, {}).get("new_visits", 0),
                    "repeat_visits": by_month.get(m, {}).get("repeat_visits", 0)} for m in months]
        return {"year": year, "total_visits": total, "unique_patients": unique,
                "repeat_visits": repeat, "status_counts": {r["status"]: r["n"] for r in statuses},
                "monthly": monthly}

    @router.get("/analytics/api/patients")
    def patients(request: Request, search: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        if not allowed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        term = f"%{search.strip()}%"
        with closing(db_factory()) as c:
            rows = c.execute("""
                SELECT t.phone, MAX(t.name) name, COUNT(*) visits, MIN(t.day) first_visit, MAX(t.day) last_visit,
                (SELECT x.doctor FROM tokens x WHERE x.phone=t.phone ORDER BY x.created DESC LIMIT 1) last_doctor,
                (SELECT x.no FROM tokens x WHERE x.phone=t.phone ORDER BY x.created DESC LIMIT 1) last_token,
                (SELECT x.created FROM tokens x WHERE x.phone=t.phone ORDER BY x.created DESC LIMIT 1) last_token_time,
                (SELECT x.status FROM tokens x WHERE x.phone=t.phone ORDER BY x.created DESC LIMIT 1) last_status
                FROM tokens t WHERE (?='' OR t.name LIKE ? OR t.phone LIKE ?)
                GROUP BY t.phone ORDER BY MAX(t.created) DESC LIMIT ? OFFSET ?
            """, (search.strip(), term, term, limit, offset)).fetchall()
            count = c.execute("""SELECT COUNT(*) FROM (SELECT phone FROM tokens
                WHERE (?='' OR name LIKE ? OR phone LIKE ?) GROUP BY phone)""",
                (search.strip(), term, term)).fetchone()[0]
        return {"total": count, "patients": [dict(r) for r in rows], "limit": limit, "offset": offset}

    @router.get("/analytics/api/patient/{phone}")
    def patient_history(request: Request, phone: str):
        if not allowed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        with closing(db_factory()) as c:
            rows = c.execute("""SELECT day,no,doctor,status,created,called,finished
                FROM tokens WHERE phone=? ORDER BY created DESC LIMIT 200""", (phone,)).fetchall()
        if not rows:
            return JSONResponse({"error": "patient not found"}, status_code=404)
        return {"phone": phone, "visits": [dict(r) for r in rows]}

    return router
