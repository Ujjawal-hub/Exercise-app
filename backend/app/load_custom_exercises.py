"""Load my custom exercises (ones wger does not have) from data/custom_exercises.json.

Run from the project root, AFTER the wger import and BEFORE the form loader:
    .venv\\Scripts\\python -m backend.app.ingest_wger
    .venv\\Scripts\\python -m backend.app.load_custom_exercises
    .venv\\Scripts\\python -m backend.app.load_form_content

Why after the wger import: my JSON uses names like "Legs" and "Quads", and those
are looked up in the categories / equipment / muscles tables that wger fills.

My JSON is the source of truth:
- an exercise in the JSON is added, or updated if it is already there (by its "id")
- its muscle and equipment links are rebuilt, so they always match the JSON
- a custom exercise that is no longer in the JSON is removed from the database
  (but only if no form guide still points at it)
Safe to run again. wger exercises (source = 'wger') are never touched.
"""

import json

from backend.app.db import CUSTOM_ID_START, PROJECT_ROOT, create_tables, get_connection

CUSTOM_FILE = PROJECT_ROOT / "data" / "custom_exercises.json"


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

def blank_to_none(value):
    """Treat "", "   " and null the same: store NULL."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def is_text_list(value):
    return isinstance(value, list) and all(is_text(item) for item in value)


# ------------------------------------------------------------
# Step 1: read and check the JSON (nothing is written yet)
# ------------------------------------------------------------

def read_entries():
    # utf-8-sig reads files with AND without a BOM (see PROBLEMS.md #2).
    with open(CUSTOM_FILE, encoding="utf-8-sig") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as error:
            raise SystemExit(f"Stopped: {CUSTOM_FILE.name} is not valid JSON: {error}")
    return data.get("exercises") or []


def check_entry(entry):
    """Return a list of problems with one entry (empty list = it is fine)."""
    if not isinstance(entry, dict):
        return ["is not an object { ... }"]
    problems = []
    exercise_id = entry.get("id")
    if not isinstance(exercise_id, int) or isinstance(exercise_id, bool):
        problems.append('"id" must be a whole number, e.g. 1000000')
    elif exercise_id < CUSTOM_ID_START:
        problems.append(f'"id" must be {CUSTOM_ID_START} or more (lower ids belong to wger)')
    if not is_text(entry.get("name")):
        problems.append('"name" is missing or empty')
    if not isinstance(entry.get("reviewed"), bool):
        problems.append('"reviewed" must be true or false (no quotes)')
    if not is_text(entry.get("category")):
        problems.append('"category" is missing or empty')
    if not is_text(entry.get("source_name")):
        problems.append('"source_name" is missing or empty')
    for key in ("equipment", "muscles_primary", "muscles_secondary"):
        if entry.get(key) is not None and not is_text_list(entry.get(key)):
            problems.append(f'"{key}" must be a list of names, e.g. ["Quads"]')
    return problems


def check_all(entries):
    """Return a list of problems in the whole file (empty list = all fine)."""
    errors = []
    seen_ids, seen_names = set(), set()
    for entry in entries:
        name_shown = entry.get("name") if isinstance(entry, dict) else repr(entry)
        errors += [f"{name_shown}: {problem}" for problem in check_entry(entry)]
        if not isinstance(entry, dict):
            continue
        if entry.get("id") in seen_ids:
            errors.append(f"{name_shown}: id {entry.get('id')} is used twice")
        seen_ids.add(entry.get("id"))
        name = str(entry.get("name") or "").strip().lower()
        if name in seen_names:
            errors.append(f"{name_shown}: name is used twice")
        seen_names.add(name)
    return errors


# ------------------------------------------------------------
# Step 2: turn names into ids (still nothing written)
# ------------------------------------------------------------

def find_category(conn, name):
    row = conn.execute(
        "SELECT id FROM categories WHERE lower(name) = lower(?)", (name.strip(),)
    ).fetchone()
    return row["id"] if row else None


def find_equipment(conn, name):
    row = conn.execute(
        "SELECT id FROM equipment WHERE lower(name) = lower(?)", (name.strip(),)
    ).fetchone()
    return row["id"] if row else None


def find_muscle(conn, name):
    """Match the common name ("Quads") or the Latin name ("Trapezius")."""
    row = conn.execute(
        "SELECT id FROM muscles WHERE lower(name_en) = lower(?) OR lower(name) = lower(?)",
        (name.strip(), name.strip()),
    ).fetchone()
    return row["id"] if row else None


def resolve(conn, entry, errors):
    """Look up every name in one entry. Unknown names are added to errors."""
    label = entry["name"].strip()
    category_id = find_category(conn, entry["category"])
    if category_id is None:
        errors.append(f'{label}: category "{entry["category"]}" not found')

    equipment_ids = []
    for name in entry.get("equipment") or []:
        found = find_equipment(conn, name)
        if found is None:
            errors.append(f'{label}: equipment "{name}" not found')
        else:
            equipment_ids.append(found)

    muscle_links = []  # (muscle_id, is_primary)
    for is_primary, key in ((1, "muscles_primary"), (0, "muscles_secondary")):
        for name in entry.get(key) or []:
            found = find_muscle(conn, name)
            if found is None:
                errors.append(f'{label}: muscle "{name}" not found')
            else:
                muscle_links.append((found, is_primary))

    return {"category_id": category_id, "equipment_ids": equipment_ids,
            "muscle_links": muscle_links}


# ------------------------------------------------------------
# Step 3: write everything in one transaction
# ------------------------------------------------------------

def save_exercise(conn, entry, ids):
    exercise_id = entry["id"]
    conn.execute(
        "INSERT INTO exercises (id, name, category_id, source, source_name, source_url, "
        "reviewed) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, "
        "category_id = excluded.category_id, source = excluded.source, "
        "source_name = excluded.source_name, source_url = excluded.source_url, "
        "reviewed = excluded.reviewed",
        (
            exercise_id,
            entry["name"].strip(),
            ids["category_id"],
            "custom",
            entry["source_name"].strip(),
            blank_to_none(entry.get("source_url")),
            1 if entry["reviewed"] else 0,
        ),
    )
    # Link tables: remove this exercise's old links, then add the current ones.
    conn.execute("DELETE FROM exercise_muscles WHERE exercise_id = ?", (exercise_id,))
    conn.execute("DELETE FROM exercise_equipment WHERE exercise_id = ?", (exercise_id,))
    for muscle_id, is_primary in ids["muscle_links"]:
        conn.execute(
            "INSERT OR IGNORE INTO exercise_muscles (exercise_id, muscle_id, is_primary) "
            "VALUES (?, ?, ?)",
            (exercise_id, muscle_id, is_primary),
        )
    for equipment_id in ids["equipment_ids"]:
        conn.execute(
            "INSERT OR IGNORE INTO exercise_equipment (exercise_id, equipment_id) VALUES (?, ?)",
            (exercise_id, equipment_id),
        )


def find_removed(conn, keep_ids):
    """Custom exercises in the database that are no longer in my JSON."""
    rows = conn.execute("SELECT id, name FROM exercises WHERE source = ?", ("custom",)).fetchall()
    return [row for row in rows if row["id"] not in keep_ids]


def remove_exercise(conn, exercise_id):
    conn.execute("DELETE FROM exercise_muscles WHERE exercise_id = ?", (exercise_id,))
    conn.execute("DELETE FROM exercise_equipment WHERE exercise_id = ?", (exercise_id,))
    conn.execute("DELETE FROM main_images WHERE exercise_id = ?", (exercise_id,))
    conn.execute("DELETE FROM exercises WHERE id = ? AND source = ?", (exercise_id, "custom"))


def stop(errors):
    print("Stopped: please fix these first. Nothing was written.")
    for error in errors:
        print("  -", error)
    raise SystemExit(1)


def main():
    create_tables()  # also adds the new columns to an older app.db

    entries = read_entries()
    errors = check_all(entries)
    if errors:
        stop(errors)

    conn = get_connection()
    try:
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            stop(["the wger tables are empty. Run the wger import first."])

        # Look up all names before writing anything, so a typo stops the whole run.
        resolved = [(entry, resolve(conn, entry, errors)) for entry in entries]

        # A removed exercise must not still have a form guide pointing at it.
        removed = find_removed(conn, {entry["id"] for entry in entries})
        for row in removed:
            guide = conn.execute(
                "SELECT name FROM form_guides WHERE exercise_id = ?", (row["id"],)
            ).fetchone()
            if guide:
                errors.append(
                    f'{row["name"]} is no longer in {CUSTOM_FILE.name}, but the form guide '
                    f'"{guide["name"]}" still points at it. Remove the guide from the form '
                    "JSON and run load_form_content first."
                )
        if errors:
            stop(errors)

        for row in removed:
            remove_exercise(conn, row["id"])
        for entry, ids in resolved:
            save_exercise(conn, entry, ids)
        conn.commit()      # everything is saved together...
    except Exception:
        conn.rollback()    # ...or nothing is, if anything went wrong
        raise
    finally:
        conn.close()

    drafts = sum(1 for entry in entries if not entry["reviewed"])
    print(f"Saved {len(entries)} custom exercises "
          f"({len(entries) - drafts} reviewed, {drafts} not reviewed yet).")
    if removed:
        print(f"Removed {len(removed)} no longer in the JSON: "
              f"{', '.join(row['name'] for row in removed)}")


if __name__ == "__main__":
    main()
