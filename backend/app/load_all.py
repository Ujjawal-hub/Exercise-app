"""Run all my loaders in the right order. Use this after editing any of my files.

Run from the project root:
    .venv\\Scripts\\python -m backend.app.load_all

The wger import is NOT included (it downloads from the internet and is only
needed once, or when I want fresh wger data). Run it first on a new database:
    .venv\\Scripts\\python -m backend.app.ingest_wger

If one loader stops with a problem, the ones after it do not run.
"""

from backend.app import load_custom_exercises, load_form_content, load_images, load_routines

# Order matters: guides need their exercises, pictures need their guides.
STEPS = [
    ("custom exercises", load_custom_exercises),
    ("form guides", load_form_content),
    ("routines", load_routines),
    ("pictures", load_images),
]


def main():
    for label, module in STEPS:
        print(f"\n=== Loading {label} ===")
        module.main()
    print("\nAll done.")


if __name__ == "__main__":
    main()
