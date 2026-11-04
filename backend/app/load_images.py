"""Load my pictures from data/form_images/ and data/main_images/ into the database.

Run from the project root, AFTER load_form_content (pictures belong to a guide):
    .venv\\Scripts\\python -m backend.app.load_images

Folders: each folder is named after a guide, in lower case with "-" between words:
    "Push-ups" -> push-ups,  "DB Shoulder Press" -> db-shoulder-press
Files: named 1, 2, 3 ... (+ .png / .jpg / .jpeg / .webp / .gif) = display order.
    form_images/<folder>/  -> posture pictures shown with the guide
    main_images/<folder>/  -> main pictures, shown INSTEAD of wger's for that exercise

Only the file PATH is saved in the database, not the picture itself.
The folders are the source of truth: every run, both picture tables are emptied
and filled again from the folders, in one transaction. Safe to run again.
"""

import re

from backend.app.db import PROJECT_ROOT, create_tables, get_connection

DATA_DIR = PROJECT_ROOT / "data"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IGNORED_FILES = {"desktop.ini", "thumbs.db"}  # files Windows creates by itself


def folder_name(guide_name):
    """'DB Shoulder Press' -> 'db-shoulder-press'."""
    return re.sub(r"[^a-z0-9]+", "-", guide_name.lower()).strip("-")


def scan(kind, guides, errors):
    """Read one picture folder (form_images or main_images).

    Returns a list of (folder, position, file_path). Problems go into errors.
    """
    root = DATA_DIR / kind
    found = []
    if not root.is_dir():
        return found
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name not in guides:
            errors.append(f"{kind}/{folder.name}/: no guide has this name (typo in the folder name?)")
            continue
        positions = {}
        for file in sorted(folder.iterdir()):
            if file.name.startswith(".") or file.name.lower() in IGNORED_FILES:
                continue
            where = f"{kind}/{folder.name}/{file.name}"
            if not file.is_file():
                errors.append(f"{where}: folders inside picture folders are not used")
            elif file.suffix.lower() not in IMAGE_TYPES:
                errors.append(f"{where}: not a picture (use .png, .jpg, .jpeg, .webp or .gif)")
            elif not file.stem.isdigit() or int(file.stem) < 1:
                errors.append(f"{where}: name must be a number from 1 up, e.g. 1.png")
            elif int(file.stem) in positions:
                errors.append(f"{where}: number {int(file.stem)} is used twice "
                              f"(also {positions[int(file.stem)]})")
            else:
                positions[int(file.stem)] = file.name
                # Always "/" in the saved path, so it also works as a web address.
                found.append((folder.name, int(file.stem), f"{kind}/{folder.name}/{file.name}"))
    return found


def main():
    create_tables()

    conn = get_connection()
    try:
        # folder name -> the guide's id and its exercise's id
        guides = {
            folder_name(row["name"]): (row["id"], row["exercise_id"])
            for row in conn.execute("SELECT id, exercise_id, name FROM form_guides").fetchall()
        }
        if not guides:
            raise SystemExit("Stopped: there are no form guides yet. Run load_form_content first.")

        errors = []
        form_pictures = scan("form_images", guides, errors)
        main_pictures = scan("main_images", guides, errors)
        if errors:
            print("Stopped: please fix these first. Nothing was written.")
            for error in errors:
                print("  -", error)
            raise SystemExit(1)

        conn.execute("DELETE FROM form_images")
        conn.execute("DELETE FROM main_images")
        for folder, position, path in form_pictures:
            guide_id, _ = guides[folder]
            conn.execute(
                "INSERT INTO form_images (guide_id, position, file_path) VALUES (?, ?, ?)",
                (guide_id, position, path),
            )
        for folder, position, path in main_pictures:
            _, exercise_id = guides[folder]
            conn.execute(
                "INSERT INTO main_images (exercise_id, position, file_path) VALUES (?, ?, ?)",
                (exercise_id, position, path),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Saved {len(form_pictures)} form pictures and {len(main_pictures)} main pictures.")
    for kind, pictures in (("form", form_pictures), ("main", main_pictures)):
        folders = sorted({folder for folder, _, _ in pictures})
        if folders:
            print(f"  {kind} pictures for: {', '.join(folders)}")


if __name__ == "__main__":
    main()
