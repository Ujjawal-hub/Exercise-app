-- Database design for the Exercise Form Guide.
-- "IF NOT EXISTS" makes this safe to run again: existing tables are left alone.

-- ============================================================
-- wger catalogue (filled by the wger ingestion script)
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY,          -- same id as in wger
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS muscles (
    id       INTEGER PRIMARY KEY,      -- same id as in wger
    name     TEXT NOT NULL,            -- Latin name, e.g. "Biceps femoris"
    name_en  TEXT,                     -- common name, e.g. "Hamstrings" (can be empty)
    is_front INTEGER NOT NULL          -- 1 = front of body, 0 = back
);

CREATE TABLE IF NOT EXISTS equipment (
    id   INTEGER PRIMARY KEY,          -- same id as in wger
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercises (
    id             INTEGER PRIMARY KEY,  -- same id as in wger
    uuid           TEXT,
    name           TEXT NOT NULL,        -- English name
    description    TEXT,                 -- English description as plain text (can be empty)
    category_id    INTEGER REFERENCES categories(id),
    license_name   TEXT,                 -- e.g. "CC-BY-SA 4"
    license_url    TEXT,
    license_author TEXT                  -- who wrote it, for the credit line
);

-- Link table: which muscles an exercise works.
-- is_primary = 1 for main muscles, 0 for secondary (helper) muscles.
CREATE TABLE IF NOT EXISTS exercise_muscles (
    exercise_id INTEGER NOT NULL REFERENCES exercises(id),
    muscle_id   INTEGER NOT NULL REFERENCES muscles(id),
    is_primary  INTEGER NOT NULL,
    PRIMARY KEY (exercise_id, muscle_id, is_primary)
);

-- Link table: which equipment an exercise uses.
CREATE TABLE IF NOT EXISTS exercise_equipment (
    exercise_id  INTEGER NOT NULL REFERENCES exercises(id),
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    PRIMARY KEY (exercise_id, equipment_id)
);

CREATE TABLE IF NOT EXISTS exercise_images (
    id             INTEGER PRIMARY KEY,  -- same id as in wger
    exercise_id    INTEGER NOT NULL REFERENCES exercises(id),
    url            TEXT NOT NULL,
    thumbnail_url  TEXT,
    is_main        INTEGER NOT NULL DEFAULT 0,
    license_author TEXT
);

-- ============================================================
-- Form layer (filled ONLY from data/form_content.json)
-- The wger ingestion script must never write to these tables.
-- ============================================================

CREATE TABLE IF NOT EXISTS form_guides (
    id          INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL UNIQUE REFERENCES exercises(id),  -- one guide per exercise
    setup       TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url  TEXT
);

-- One row per step. step_number keeps the order.
CREATE TABLE IF NOT EXISTS form_steps (
    id          INTEGER PRIMARY KEY,
    guide_id    INTEGER NOT NULL REFERENCES form_guides(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    text        TEXT NOT NULL,
    UNIQUE (guide_id, step_number)
);

-- One row per common mistake, with how to fix it.
CREATE TABLE IF NOT EXISTS form_mistakes (
    id       INTEGER PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES form_guides(id) ON DELETE CASCADE,
    mistake  TEXT NOT NULL,
    fix      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routines (
    id          INTEGER PRIMARY KEY,
    body_part   TEXT NOT NULL,           -- e.g. "legs", "shoulders"
    kind        TEXT NOT NULL CHECK (kind IN ('warmup', 'cooldown')),
    name        TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url  TEXT
);

-- One row per move in a routine. step_number keeps the order.
CREATE TABLE IF NOT EXISTS routine_steps (
    id          INTEGER PRIMARY KEY,
    routine_id  INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    instruction TEXT NOT NULL,
    amount      TEXT,                    -- e.g. "30 seconds" or "10 reps" (can be empty)
    UNIQUE (routine_id, step_number)
);
