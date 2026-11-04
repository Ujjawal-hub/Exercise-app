"""Load my warmup and cooldown routines from data/form_content/*.json ("routines" lists).

Run from the project root (any time, it does not need the other loaders):
    .venv\\Scripts\\python -m backend.app.load_routines

Same rules as the other loaders: check everything first, write in one transaction,
upsert each routine (found again by body part + warmup/cooldown), rebuild its steps,
and remove routines that are no longer in the JSON. Safe to run again.
"""

import json

from backend.app.db import PROJECT_ROOT, create_tables, get_connection

FORM_DIR = PROJECT_ROOT / "data" / "form_content"
KINDS = ("warmup", "cooldown")


def blank_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def read_routines():
    """Return a list of (file name, routine) from every JSON file."""
    files = sorted(FORM_DIR.glob("*.json"))
    if not files:
        raise SystemExit(f"Stopped: no .json files found in {FORM_DIR}")
    routines = []
    for path in files:
        with open(path, encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as error:
                raise SystemExit(f"Stopped: {path.name} is not valid JSON: {error}")
        for routine in data.get("routines") or []:
            routines.append((path.name, routine))
    return routines


def check_routine(routine):
    """Return a list of problems with one routine (empty list = it is fine)."""
    if not isinstance(routine, dict):
        return ["is not an object { ... }"]
    problems = []
    if not is_text(routine.get("body_part")):
        problems.append('"body_part" is missing or empty')
    if routine.get("kind") not in KINDS:
        problems.append('"kind" must be "warmup" or "cooldown"')
    if not is_text(routine.get("name")):
        problems.append('"name" is missing or empty')
    if not is_text(routine.get("source_name")):
        problems.append('"source_name" is missing or empty')
    if not isinstance(routine.get("reviewed"), bool):
        problems.append('"reviewed" must be true or false (no quotes)')
    steps = routine.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append('"steps" must be a list with at least one step')
    else:
        for number, step in enumerate(steps, start=1):
            if not isinstance(step, dict) or not is_text(step.get("instruction")):
                problems.append(f'step {number} needs an "instruction"')
            elif step.get("amount") is not None and not isinstance(step.get("amount"), str):
                problems.append(f'step {number}: "amount" must be text, e.g. "10 reps"')
    return problems


def check_all(routines):
    errors = []
    seen = {}
    for file_name, routine in routines:
        name_shown = routine.get("name") if isinstance(routine, dict) else repr(routine)
        label = f"{file_name}: {name_shown}"
        errors += [f"{label}: {problem}" for problem in check_routine(routine)]
        if not isinstance(routine, dict):
            continue
        # Only one warmup and one cooldown per body part.
        key = (str(routine.get("body_part")).strip().lower(), routine.get("kind"))
        if key in seen:
            errors.append(f"{label}: a {key[1]} for {key[0]} is already in {seen[key]}")
        seen[key] = file_name
    if errors:
        print("Stopped: please fix these in the JSON first. Nothing was written.")
        for error in errors:
            print("  -", error)
        raise SystemExit(1)


def save_routine(conn, routine):
    body_part = routine["body_part"].strip().lower()  # "Legs" and "legs" are the same
    conn.execute(
        "INSERT INTO routines (body_part, kind, name, source_name, source_url, reviewed) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(body_part, kind) DO UPDATE SET name = excluded.name, "
        "source_name = excluded.source_name, source_url = excluded.source_url, "
        "reviewed = excluded.reviewed",
        (
            body_part,
            routine["kind"],
            routine["name"].strip(),
            routine["source_name"].strip(),
            blank_to_none(routine.get("source_url")),
            1 if routine["reviewed"] else 0,
        ),
    )
    routine_id = conn.execute(
        "SELECT id FROM routines WHERE body_part = ? AND kind = ?", (body_part, routine["kind"])
    ).fetchone()["id"]

    conn.execute("DELETE FROM routine_steps WHERE routine_id = ?", (routine_id,))
    for number, step in enumerate(routine["steps"], start=1):
        conn.execute(
            "INSERT INTO routine_steps (routine_id, step_number, instruction, amount) "
            "VALUES (?, ?, ?, ?)",
            (routine_id, number, step["instruction"].strip(), blank_to_none(step.get("amount"))),
        )
    return (body_part, routine["kind"])


def main():
    create_tables()  # also adds the new "reviewed" column to an older app.db

    routines = read_routines()
    check_all(routines)

    conn = get_connection()
    try:
        kept = {save_routine(conn, routine) for _, routine in routines}
        # Remove routines no longer in the JSON (their steps go too: ON DELETE CASCADE).
        removed = []
        for row in conn.execute("SELECT id, body_part, kind, name FROM routines").fetchall():
            if (row["body_part"], row["kind"]) not in kept:
                conn.execute("DELETE FROM routines WHERE id = ?", (row["id"],))
                removed.append(row["name"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    drafts = sum(1 for _, routine in routines if not routine["reviewed"])
    body_parts = sorted({routine["body_part"].strip().lower() for _, routine in routines})
    print(f"Saved {len(routines)} routines ({len(routines) - drafts} reviewed, "
          f"{drafts} not reviewed yet) for: {', '.join(body_parts)}.")
    if removed:
        print(f"Removed {len(removed)} no longer in the JSON: {', '.join(removed)}")


if __name__ == "__main__":
    main()
