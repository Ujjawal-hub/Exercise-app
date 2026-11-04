"""The web server: the page, my pictures, and the /api/... addresses the page calls.

Run from the project root:
    .venv\\Scripts\\uvicorn backend.app.main:app --reload
Then open http://127.0.0.1:8000  (and http://127.0.0.1:8000/docs to try the API).

Every /api route only READS the database. Content is changed by editing my files
and running load_all, never through the website.
"""

from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.db import PROJECT_ROOT, get_connection

FRONTEND_DIR = PROJECT_ROOT / "frontend"
FORM_IMAGES_DIR = PROJECT_ROOT / "data" / "form_images"
MAIN_IMAGES_DIR = PROJECT_ROOT / "data" / "main_images"
WGER_URL = "https://wger.de"

app = FastAPI(title="Exercise Form Guide")

# Share ONLY the two picture folders. Never the whole data/ folder: app.db is in there.
# (Git does not keep empty folders, so make sure they exist on a fresh copy.)
FORM_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
MAIN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images/form", StaticFiles(directory=FORM_IMAGES_DIR), name="form_images")
app.mount("/images/main", StaticFiles(directory=MAIN_IMAGES_DIR), name="main_images")


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

@contextmanager
def open_db():
    """Open the database for one request and always close it afterwards."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def picture_url(file_path):
    """'form_images/push-ups/1.png' -> '/images/form/push-ups/1.png' (a web address)."""
    folder, rest = file_path.split("/", 1)
    return f"/images/{folder.removesuffix('_images')}/{rest}"


def muscle_label(row):
    """Common name if wger has one ("Quads"), otherwise the Latin one ("Trapezius")."""
    return row["name_en"] or row["name"]


def thumbnail(conn, exercise_id):
    """One small picture for a tile: my main picture first, else wger's, else None."""
    row = conn.execute(
        "SELECT file_path FROM main_images WHERE exercise_id = ? ORDER BY position LIMIT 1",
        (exercise_id,),
    ).fetchone()
    if row:
        return picture_url(row["file_path"])
    row = conn.execute(
        "SELECT url, thumbnail_url FROM exercise_images WHERE exercise_id = ? "
        "ORDER BY is_main DESC, id LIMIT 1",
        (exercise_id,),
    ).fetchone()
    if row:
        return row["thumbnail_url"] or row["url"]
    return None  # the page shows a placeholder tile


# Used by every list: the exercise, its category, and its guide (if any).
TILE_SELECT = (
    "SELECT e.id, e.name AS exercise_name, c.name AS category, "
    "g.name AS guide_name, g.reviewed AS guide_reviewed "
    "FROM exercises e "
    "LEFT JOIN categories c ON c.id = e.category_id "
    "LEFT JOIN form_guides g ON g.exercise_id = e.id "
)


def tile(conn, row):
    """What a list needs for one exercise. My guide name is shown when there is one."""
    has_guide = row["guide_name"] is not None
    return {
        "id": row["id"],
        "name": row["guide_name"] if has_guide else row["exercise_name"],
        "category": row["category"],
        "thumbnail": thumbnail(conn, row["id"]),
        # None = no guide yet. Otherwise {"reviewed": true/false} for the badge.
        "guide": {"reviewed": bool(row["guide_reviewed"])} if has_guide else None,
    }


def routine_dict(conn, row):
    steps = conn.execute(
        "SELECT instruction, amount FROM routine_steps WHERE routine_id = ? ORDER BY step_number",
        (row["id"],),
    ).fetchall()
    return {
        "name": row["name"],
        "steps": [{"instruction": s["instruction"], "amount": s["amount"]} for s in steps],
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "reviewed": bool(row["reviewed"]),
    }


# ------------------------------------------------------------
# The page
# ------------------------------------------------------------

@app.get("/", include_in_schema=False)
def page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------
# Side panel and home page
# ------------------------------------------------------------

@app.get("/api/categories")
def categories():
    """Side panel: every category, with how many exercises and guides it has."""
    with open_db() as conn:
        rows = conn.execute(
            "SELECT c.id, c.name, COUNT(e.id) AS exercise_count, COUNT(g.id) AS guide_count "
            "FROM categories c "
            "LEFT JOIN exercises e ON e.category_id = c.id "
            "LEFT JOIN form_guides g ON g.exercise_id = e.id "
            "GROUP BY c.id ORDER BY c.name"
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/routines")
def routine_list():
    """Side panel: the body parts that have a warmup and/or cooldown."""
    with open_db() as conn:
        rows = conn.execute(
            "SELECT body_part, kind FROM routines ORDER BY body_part, kind DESC"
        ).fetchall()
    body_parts = {}
    for row in rows:
        body_parts.setdefault(row["body_part"], []).append(row["kind"])
    return [{"body_part": part, "kinds": kinds} for part, kinds in body_parts.items()]


@app.get("/api/guides")
def guides():
    """Home page: all exercises that have my form guide, A-Z."""
    with open_db() as conn:
        rows = conn.execute(TILE_SELECT + "WHERE g.id IS NOT NULL ORDER BY g.name").fetchall()
        return [tile(conn, row) for row in rows]


# ------------------------------------------------------------
# Category page and search
# ------------------------------------------------------------

@app.get("/api/categories/{category_id}/exercises")
def category_exercises(
    category_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Category page: my guides first (all of them), then other exercises, 50 at a time."""
    with open_db() as conn:
        category = conn.execute(
            "SELECT id, name FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")

        guide_rows = conn.execute(
            TILE_SELECT + "WHERE e.category_id = ? AND g.id IS NOT NULL ORDER BY g.name",
            (category_id,),
        ).fetchall()
        total_others = conn.execute(
            "SELECT COUNT(*) FROM exercises e LEFT JOIN form_guides g ON g.exercise_id = e.id "
            "WHERE e.category_id = ? AND g.id IS NULL",
            (category_id,),
        ).fetchone()[0]
        other_rows = conn.execute(
            TILE_SELECT + "WHERE e.category_id = ? AND g.id IS NULL "
            "ORDER BY e.name COLLATE NOCASE LIMIT ? OFFSET ?",
            (category_id, limit, offset),
        ).fetchall()

        next_offset = offset + limit
        return {
            "category": dict(category),
            "guides": [tile(conn, row) for row in guide_rows],
            "others": [tile(conn, row) for row in other_rows],
            "total_others": total_others,
            # None when there are no more: the page hides its "Show more" button.
            "next_offset": next_offset if next_offset < total_others else None,
        }


@app.get("/api/search")
def search(q: str = Query("", max_length=100)):
    """Search box dropdown: up to 10 matches, my guides first.

    Looks in both names: mine ("DB Shoulder Press") and wger's ("Shoulder Press, Dumbbells").
    """
    q = q.strip()
    if len(q) < 2:
        return []
    # % and _ are wildcards in LIKE. Put a \ before them so they are searched as normal
    # characters. The text still goes in as a ? value, never joined into the SQL.
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    starts = pattern[1:]  # "squat%": names that START with the text come first
    with open_db() as conn:
        rows = conn.execute(
            TILE_SELECT
            + "WHERE e.name LIKE ? ESCAPE '\\' OR g.name LIKE ? ESCAPE '\\' "
            "ORDER BY g.id IS NULL, "
            "(e.name LIKE ? ESCAPE '\\' OR g.name LIKE ? ESCAPE '\\') DESC, "
            "COALESCE(g.name, e.name) COLLATE NOCASE "
            "LIMIT 10",
            (pattern, pattern, starts, starts),
        ).fetchall()
        return [tile(conn, row) for row in rows]


# ------------------------------------------------------------
# Exercise page
# ------------------------------------------------------------

@app.get("/api/exercises/{exercise_id}")
def exercise(exercise_id: int):
    """Exercise page: everything about one exercise in one answer."""
    with open_db() as conn:
        ex = conn.execute(
            "SELECT e.*, c.name AS category FROM exercises e "
            "LEFT JOIN categories c ON c.id = e.category_id WHERE e.id = ?",
            (exercise_id,),
        ).fetchone()
        if ex is None:
            raise HTTPException(status_code=404, detail="Exercise not found")

        equipment = conn.execute(
            "SELECT q.name FROM exercise_equipment l JOIN equipment q ON q.id = l.equipment_id "
            "WHERE l.exercise_id = ? ORDER BY q.name",
            (exercise_id,),
        ).fetchall()
        muscles = conn.execute(
            "SELECT m.name, m.name_en, l.is_primary FROM exercise_muscles l "
            "JOIN muscles m ON m.id = l.muscle_id WHERE l.exercise_id = ? "
            "ORDER BY COALESCE(m.name_en, m.name)",
            (exercise_id,),
        ).fetchall()

        # Pictures: mine replace wger's when I have any (see PROBLEMS.md #6).
        mine = conn.execute(
            "SELECT file_path FROM main_images WHERE exercise_id = ? ORDER BY position",
            (exercise_id,),
        ).fetchall()
        if mine:
            images = [{"url": picture_url(r["file_path"]), "author": None, "from_wger": False}
                      for r in mine]
        else:
            wger_images = conn.execute(
                "SELECT url, license_author FROM exercise_images WHERE exercise_id = ? "
                "ORDER BY is_main DESC, id",
                (exercise_id,),
            ).fetchall()
            images = [{"url": r["url"], "author": r["license_author"], "from_wger": True}
                      for r in wger_images]

        if ex["source"] == "custom":
            credit = {
                "type": "custom",
                "source_name": ex["source_name"],
                "source_url": ex["source_url"],
                "reviewed": bool(ex["reviewed"]),
            }
        else:
            credit = {
                "type": "wger",
                "site_url": WGER_URL,
                "license_name": ex["license_name"],
                "license_url": ex["license_url"],
                "author": ex["license_author"],
            }

        guide = None
        g = conn.execute("SELECT * FROM form_guides WHERE exercise_id = ?", (exercise_id,)).fetchone()
        if g:
            steps = conn.execute(
                "SELECT text FROM form_steps WHERE guide_id = ? ORDER BY step_number", (g["id"],)
            ).fetchall()
            mistakes = conn.execute(
                "SELECT mistake, fix FROM form_mistakes WHERE guide_id = ? ORDER BY id", (g["id"],)
            ).fetchall()
            form_pictures = conn.execute(
                "SELECT file_path FROM form_images WHERE guide_id = ? ORDER BY position", (g["id"],)
            ).fetchall()
            guide = {
                "name": g["name"],
                "setup": g["setup"],
                "steps": [s["text"] for s in steps],
                "mistakes": [{"mistake": m["mistake"], "fix": m["fix"]} for m in mistakes],
                "form_images": [picture_url(p["file_path"]) for p in form_pictures],
                "demo_url": g["demo_url"],
                "source_name": g["source_name"],
                "source_url": g["source_url"],
                "reviewed": bool(g["reviewed"]),
            }

    return {
        "id": ex["id"],
        "name": guide["name"] if guide else ex["name"],
        "wger_name": ex["name"] if ex["source"] == "wger" else None,
        "category": ex["category"],
        "description": ex["description"],  # wger's text; None if it has none
        "equipment": [r["name"] for r in equipment],
        "muscles": {
            "primary": [muscle_label(m) for m in muscles if m["is_primary"]],
            "secondary": [muscle_label(m) for m in muscles if not m["is_primary"]],
        },
        "images": images,
        "credit": credit,
        "guide": guide,  # None -> the page says "form guide not written yet"
    }


# ------------------------------------------------------------
# Routine page
# ------------------------------------------------------------

@app.get("/api/routines/{body_part}")
def routine(body_part: str):
    """Routine page: the warmup and cooldown for one body part."""
    with open_db() as conn:
        rows = conn.execute(
            "SELECT * FROM routines WHERE body_part = ?", (body_part.strip().lower(),)
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="No routines for this body part")
        by_kind = {row["kind"]: routine_dict(conn, row) for row in rows}
    return {
        "body_part": rows[0]["body_part"],
        "warmup": by_kind.get("warmup"),
        "cooldown": by_kind.get("cooldown"),
    }
