"""Load my form guides from data/form_content/*.json into data/app.db.

Run from the project root, AFTER the wger import:
    .venv\\Scripts\\python -m backend.app.load_form_content

My JSON files are the source of truth. The database is only a copy of them:
- a guide in the JSON is added, or updated if it is already there
- its steps and mistakes are rebuilt, so they always match the JSON exactly
- a guide that is no longer in the JSON is removed from the database
Safe to run again: running it twice gives the same result.

Only the form tables are written (form_guides, form_steps, form_mistakes).
The wger tables are only read, to find each guide's exercise.
"""

import json
from urllib.parse import urlparse

from backend.app.db import PROJECT_ROOT, create_tables, get_connection

FORM_DIR = PROJECT_ROOT / "data" / "form_content"
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

def blank_to_none(value):
    """Treat "", "   " and null the same: store NULL."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def is_youtube(url):
    """True only for youtube.com / youtu.be links."""
    return (urlparse(url).hostname or "").lower() in YOUTUBE_HOSTS


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


# ------------------------------------------------------------
# Step 1: read and check every JSON file (nothing is written yet)
# ------------------------------------------------------------

def read_entries():
    """Return a list of (file name, entry) for every exercise in every file."""
    files = sorted(FORM_DIR.glob("*.json"))
    if not files:
        raise SystemExit(f"Stopped: no .json files found in {FORM_DIR}")
    entries = []
    for path in files:
        # utf-8-sig reads files with AND without a BOM (see PROBLEMS.md #2).
        with open(path, encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as error:
                raise SystemExit(f"Stopped: {path.name} is not valid JSON: {error}")
        for entry in data.get("exercises") or []:
            entries.append((path.name, entry))
    return entries


def check_entry(entry):
    """Return a list of problems with one entry (empty list = it is fine)."""
    problems = []
    if not isinstance(entry, dict):
        return ["is not an object { ... }"]
    if not is_text(entry.get("exercise")):
        problems.append('"exercise" (the name) is missing or empty')
    if not is_text(entry.get("setup")):
        problems.append('"setup" is missing or empty')
    if not is_text(entry.get("source_name")):
        problems.append('"source_name" is missing or empty')
    # Must be exactly true or false. The text "false" would count as true in Python.
    if not isinstance(entry.get("reviewed"), bool):
        problems.append('"reviewed" must be true or false (no quotes)')

    wger_id = entry.get("wger_id")
    if wger_id is None:
        if not is_text(entry.get("custom_exercise")):
            problems.append('"wger_id" is null, so "custom_exercise" must name my exercise')
    elif not isinstance(wger_id, int) or isinstance(wger_id, bool):
        problems.append('"wger_id" must be a whole number or null')

    steps = entry.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append('"steps" must be a list with at least one step')
    elif not all(is_text(step) for step in steps):
        problems.append('every step must be non-empty text')

    mistakes = entry.get("mistakes")
    if mistakes is None:
        mistakes = []
    if not isinstance(mistakes, list):
        problems.append('"mistakes" must be a list')
    else:
        for number, item in enumerate(mistakes, start=1):
            if not isinstance(item, dict) or not is_text(item.get("mistake")) or not is_text(item.get("fix")):
                problems.append(f'mistake {number} needs both "mistake" and "fix"')
    return problems


def check_all(entries):
    """Stop before writing anything if any entry has a problem."""
    errors = []
    seen_names, seen_targets = {}, {}
    for file_name, entry in entries:
        name_shown = entry.get("exercise") if isinstance(entry, dict) else repr(entry)
        label = f"{file_name}: {name_shown}"
        for problem in check_entry(entry):
            errors.append(f"{label}: {problem}")
        if not isinstance(entry, dict):
            continue

        # The same guide name twice? (form_guides.name must be unique)
        name = str(entry.get("exercise") or "").strip().lower()
        if name in seen_names:
            errors.append(f"{label}: same name as an entry in {seen_names[name]}")
        seen_names[name] = file_name

        # Two guides for the same exercise? (one guide per exercise)
        target = entry.get("wger_id") or ("custom", str(entry.get("custom_exercise")).strip().lower())
        if target in seen_targets:
            errors.append(f"{label}: same exercise as an entry in {seen_targets[target]}")
        seen_targets[target] = file_name

    if errors:
        print("Stopped: please fix these in the JSON first. Nothing was written.")
        for error in errors:
            print("  -", error)
        raise SystemExit(1)


# ------------------------------------------------------------
# Step 2: write everything in one transaction
# ------------------------------------------------------------

def find_exercise_id(conn, entry):
    """The exercises.id this guide belongs to, or None if it is not in the database."""
    if entry.get("wger_id") is not None:
        row = conn.execute(
            "SELECT id FROM exercises WHERE id = ? AND source = ?", (entry["wger_id"], "wger")
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM exercises WHERE source = ? AND name = ?",
            ("custom", entry["custom_exercise"].strip()),
        ).fetchone()
    return row["id"] if row else None


def remove_old_guides(conn, keep_exercise_ids):
    """Delete guides whose exercise is no longer in my JSON. Returns their names.

    Their steps and mistakes go too (ON DELETE CASCADE in schema.sql).
    """
    removed = []
    for row in conn.execute("SELECT id, exercise_id, name FROM form_guides").fetchall():
        if row["exercise_id"] not in keep_exercise_ids:
            conn.execute("DELETE FROM form_guides WHERE id = ?", (row["id"],))
            removed.append(row["name"])
    return removed


def save_guide(conn, exercise_id, entry, demo_url):
    conn.execute(
        "INSERT INTO form_guides (exercise_id, name, setup, source_name, source_url, "
        "demo_url, reviewed) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(exercise_id) DO UPDATE SET name = excluded.name, "
        "setup = excluded.setup, source_name = excluded.source_name, "
        "source_url = excluded.source_url, demo_url = excluded.demo_url, "
        "reviewed = excluded.reviewed",
        (
            exercise_id,
            entry["exercise"].strip(),
            entry["setup"].strip(),
            entry["source_name"].strip(),
            blank_to_none(entry.get("source_url")),
            demo_url,
            1 if entry["reviewed"] else 0,
        ),
    )
    # Upsert keeps the same guide id, so pictures linked to it are not lost.
    guide_id = conn.execute(
        "SELECT id FROM form_guides WHERE exercise_id = ?", (exercise_id,)
    ).fetchone()["id"]

    # Steps and mistakes: delete this guide's old rows, insert the current ones.
    # That way a removed or reordered step in the JSON is removed or reordered here too.
    conn.execute("DELETE FROM form_steps WHERE guide_id = ?", (guide_id,))
    conn.execute("DELETE FROM form_mistakes WHERE guide_id = ?", (guide_id,))
    for number, text in enumerate(entry["steps"], start=1):
        conn.execute(
            "INSERT INTO form_steps (guide_id, step_number, text) VALUES (?, ?, ?)",
            (guide_id, number, text.strip()),
        )
    for item in entry.get("mistakes") or []:
        conn.execute(
            "INSERT INTO form_mistakes (guide_id, mistake, fix) VALUES (?, ?, ?)",
            (guide_id, item["mistake"].strip(), item["fix"].strip()),
        )


def main():
    create_tables()  # also adds the new "reviewed" column to an older app.db

    entries = read_entries()
    check_all(entries)
    print(f"Read {len(entries)} guides from {FORM_DIR.name}/, all look fine.")

    saved, drafts = 0, 0
    not_found, demo_skipped = [], []
    conn = get_connection()
    try:
        # First find every guide's exercise, so old guides can be removed BEFORE
        # saving (otherwise a moved guide could clash with its own old row's name).
        found = []
        for file_name, entry in entries:
            exercise_id = find_exercise_id(conn, entry)
            if exercise_id is None:
                not_found.append(entry)
            else:
                found.append((exercise_id, entry))

        removed = remove_old_guides(conn, {exercise_id for exercise_id, _ in found})

        for exercise_id, entry in found:
            demo_url = blank_to_none(entry.get("demo_url"))
            if demo_url and not is_youtube(demo_url):
                demo_skipped.append((entry["exercise"], demo_url))
                demo_url = None  # only YouTube demos (PROBLEMS.md #7)
            save_guide(conn, exercise_id, entry, demo_url)
            saved += 1
            if not entry["reviewed"]:
                drafts += 1
        conn.commit()      # everything is saved together...
    except Exception:
        conn.rollback()    # ...or nothing is, if anything went wrong
        raise
    finally:
        conn.close()

    print(f"Saved {saved} guides ({saved - drafts} reviewed, {drafts} not reviewed yet).")
    if removed:
        print(f"Removed {len(removed)} guides that are no longer in the JSON: {', '.join(removed)}")
    if not_found:
        print(f"Skipped {len(not_found)} guides, their exercise is not in the database yet:")
        for entry in not_found:
            if entry.get("wger_id") is not None:
                print(f"  - {entry['exercise']}: wger id {entry['wger_id']} not found (run the wger import?)")
            else:
                print(f"  - {entry['exercise']}: custom exercise \"{entry['custom_exercise']}\" not loaded yet")
    if demo_skipped:
        print(f"Demo links skipped, not YouTube ({len(demo_skipped)}). Replace them with a YouTube link:")
        for name, url in demo_skipped:
            print(f"  - {name}: {url}")


if __name__ == "__main__":
    main()
