"""Download the wger exercise catalogue and store it in data/app.db.

Run from the project root:
    .venv\\Scripts\\python -m backend.app.ingest_wger

Safe to run again: every row is an upsert, so there are no duplicates.
Only the wger tables are written. The form tables (form_guides, form_steps,
form_mistakes, routines, routine_steps) are never touched here.
"""

from html.parser import HTMLParser

import httpx

from backend.app.db import create_tables, get_connection

START_URL = "https://wger.de/api/v2/exerciseinfo/"
START_PARAMS = {"language": 2, "limit": 100, "offset": 0}
ENGLISH = 2  # wger's language id for English


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Collects only the text from HTML, dropping the tags."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html):
    """Turn wger's HTML description into plain text. Returns None if empty."""
    if not html:
        return None
    parser = _TextExtractor()
    parser.feed(html)
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or None


def blank_to_none(value):
    """wger sometimes sends "" instead of null. Store both as NULL."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def find_english(exercise):
    """Return the English translation of an exercise, or None if it has none."""
    for translation in exercise.get("translations") or []:
        if translation.get("language") == ENGLISH and blank_to_none(translation.get("name")):
            return translation
    return None


# ------------------------------------------------------------
# Step 1: download every page (nothing is written yet)
# ------------------------------------------------------------

def download_all():
    exercises = []
    url, params = START_URL, START_PARAMS
    with httpx.Client(timeout=30, headers={"User-Agent": "exercise-form-guide (learning project)"}) as client:
        while url:
            response = client.get(url, params=params)
            response.raise_for_status()  # stop with an error if wger answers 4xx/5xx
            page = response.json()
            exercises.extend(page.get("results") or [])
            print(f"  downloaded {len(exercises)} / {page.get('count')}")
            url = page.get("next")  # None on the last page, which ends the loop
            params = None           # the "next" URL already contains limit/offset
    return exercises


# ------------------------------------------------------------
# Step 2: write everything in one transaction
# ------------------------------------------------------------

def upsert_category(conn, category):
    if not category or category.get("id") is None:
        return None
    conn.execute(
        "INSERT INTO categories (id, name) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
        (category["id"], category.get("name") or "Unknown"),
    )
    return category["id"]


def upsert_muscle(conn, muscle):
    conn.execute(
        "INSERT INTO muscles (id, name, name_en, is_front) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, "
        "name_en = excluded.name_en, is_front = excluded.is_front",
        (
            muscle["id"],
            muscle.get("name") or "Unknown",
            blank_to_none(muscle.get("name_en")),
            1 if muscle.get("is_front") else 0,
        ),
    )


def upsert_equipment(conn, item):
    conn.execute(
        "INSERT INTO equipment (id, name) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
        (item["id"], item.get("name") or "Unknown"),
    )


def save_exercise(conn, exercise, english):
    category_id = upsert_category(conn, exercise.get("category"))
    license_info = exercise.get("license") or {}

    conn.execute(
        "INSERT INTO exercises (id, uuid, name, description, category_id, "
        "license_name, license_url, license_author) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET uuid = excluded.uuid, name = excluded.name, "
        "description = excluded.description, category_id = excluded.category_id, "
        "license_name = excluded.license_name, license_url = excluded.license_url, "
        "license_author = excluded.license_author",
        (
            exercise["id"],
            exercise.get("uuid"),
            english["name"].strip(),
            html_to_text(english.get("description")),
            category_id,
            blank_to_none(license_info.get("short_name")),
            blank_to_none(license_info.get("url")),
            # Credit whoever wrote the English text; fall back to the exercise author.
            blank_to_none(english.get("license_author"))
            or blank_to_none(exercise.get("license_author")),
        ),
    )

    # Link tables: remove this exercise's old links, then add the current ones.
    conn.execute("DELETE FROM exercise_muscles WHERE exercise_id = ?", (exercise["id"],))
    conn.execute("DELETE FROM exercise_equipment WHERE exercise_id = ?", (exercise["id"],))

    for is_primary, key in ((1, "muscles"), (0, "muscles_secondary")):
        for muscle in exercise.get(key) or []:
            if muscle.get("id") is None:
                continue
            upsert_muscle(conn, muscle)
            conn.execute(
                "INSERT OR IGNORE INTO exercise_muscles (exercise_id, muscle_id, is_primary) "
                "VALUES (?, ?, ?)",
                (exercise["id"], muscle["id"], is_primary),
            )

    for item in exercise.get("equipment") or []:
        if item.get("id") is None:
            continue
        upsert_equipment(conn, item)
        conn.execute(
            "INSERT OR IGNORE INTO exercise_equipment (exercise_id, equipment_id) VALUES (?, ?)",
            (exercise["id"], item["id"]),
        )

    for image in exercise.get("images") or []:
        if image.get("id") is None or not image.get("image"):
            continue
        thumbnails = image.get("thumbnails") or {}
        conn.execute(
            "INSERT INTO exercise_images (id, exercise_id, url, thumbnail_url, is_main, "
            "license_author) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET exercise_id = excluded.exercise_id, "
            "url = excluded.url, thumbnail_url = excluded.thumbnail_url, "
            "is_main = excluded.is_main, license_author = excluded.license_author",
            (
                image["id"],
                exercise["id"],
                image["image"],
                blank_to_none(thumbnails.get("medium")),
                1 if image.get("is_main") else 0,
                blank_to_none(image.get("license_author")),
            ),
        )


def main():
    create_tables()

    print("Downloading from wger...")
    exercises = download_all()

    saved = skipped = no_description = no_images = 0
    conn = get_connection()
    try:
        for exercise in exercises:
            english = find_english(exercise)
            if english is None or exercise.get("id") is None:
                skipped += 1
                continue
            save_exercise(conn, exercise, english)
            saved += 1
            if not html_to_text(english.get("description")):
                no_description += 1
            if not exercise.get("images"):
                no_images += 1
        conn.commit()      # everything is saved together...
    except Exception:
        conn.rollback()    # ...or nothing is, if anything went wrong
        raise
    finally:
        conn.close()

    print(f"Saved {saved} exercises, skipped {skipped} (no English name).")
    print(f"  {no_description} have no description, {no_images} have no images.")


if __name__ == "__main__":
    main()
