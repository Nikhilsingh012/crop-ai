import os
from pathlib import Path
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    # Keep the API runnable in minimal environments where optional local
    # environment loading was not installed. Process environment always wins.
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/crop_ai",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scans (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT,
    crop TEXT NOT NULL,
    disease TEXT NOT NULL,
    healthy BOOLEAN NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    user_type TEXT NOT NULL DEFAULT 'farmer' CHECK (user_type IN ('farmer', 'gardener')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
CREATE TABLE IF NOT EXISTS user_locations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    location_name TEXT,
    accuracy DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id)
);
CREATE TABLE IF NOT EXISTS farms (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    location TEXT,
    state TEXT,
    district TEXT,
    area_acres DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS fields (
    id BIGSERIAL PRIMARY KEY,
    farm_id BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    area_acres DOUBLE PRECISION,
    soil_type TEXT,
    irrigation_type TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crops (
    id BIGSERIAL PRIMARY KEY,
    field_id BIGINT NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    crop_name TEXT NOT NULL,
    variety TEXT,
    season TEXT,
    sowing_date DATE,
    expected_harvest_date DATE,
    current_stage TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS soil_records (
    id BIGSERIAL PRIMARY KEY,
    field_id BIGINT NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    ph DOUBLE PRECISION,
    nitrogen DOUBLE PRECISION,
    phosphorus DOUBLE PRECISION,
    potassium DOUBLE PRECISION,
    sulphur DOUBLE PRECISION,
    zinc DOUBLE PRECISION,
    iron DOUBLE PRECISION,
    copper DOUBLE PRECISION,
    manganese DOUBLE PRECISION,
    boron DOUBLE PRECISION,
    electrical_conductivity DOUBLE PRECISION,
    organic_carbon DOUBLE PRECISION,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crop_events (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT NOT NULL REFERENCES crops(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS weather_records (
    id BIGSERIAL PRIMARY KEY,
    field_id BIGINT NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL,
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    rainfall DOUBLE PRECISION,
    wind_speed DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS risk_predictions (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT NOT NULL REFERENCES crops(id) ON DELETE CASCADE,
    risk_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    score DOUBLE PRECISION,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT REFERENCES crops(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS feedback (
    id BIGSERIAL PRIMARY KEY,
    feedback_type TEXT NOT NULL,
    reference_id BIGINT,
    rating TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS user_crops (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    crop_name TEXT NOT NULL,
    variety TEXT,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'India',
    planting_date DATE,
    growth_stage TEXT,
    mode TEXT NOT NULL DEFAULT 'farmer' CHECK (mode IN ('farmer', 'gardener')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS user_crop_id BIGINT REFERENCES user_crops(id) ON DELETE CASCADE;
CREATE TABLE IF NOT EXISTS weather_snapshots (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT NOT NULL REFERENCES user_crops(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crop_risks (
    id BIGSERIAL PRIMARY KEY,
    crop_id BIGINT NOT NULL REFERENCES user_crops(id) ON DELETE CASCADE,
    risk_level TEXT NOT NULL,
    risk_score DOUBLE PRECISION,
    result JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
ALTER TABLE crop_risks ALTER COLUMN risk_score DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_crops_user_id ON user_crops(user_id);
CREATE INDEX IF NOT EXISTS idx_weather_snapshots_crop_id ON weather_snapshots(crop_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_crop_risks_crop_id ON crop_risks(crop_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_farms_user_id ON farms(user_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_user_id ON user_locations(user_id);
CREATE INDEX IF NOT EXISTS idx_fields_farm_id ON fields(farm_id);
CREATE INDEX IF NOT EXISTS idx_crops_field_id ON crops(field_id);
CREATE INDEX IF NOT EXISTS idx_crops_status ON crops(status);
CREATE INDEX IF NOT EXISTS idx_soil_records_field_id ON soil_records(field_id);
CREATE INDEX IF NOT EXISTS idx_soil_records_recorded_at ON soil_records(recorded_at);
CREATE INDEX IF NOT EXISTS idx_crop_events_crop_id ON crop_events(crop_id);
CREATE INDEX IF NOT EXISTS idx_crop_events_event_date ON crop_events(event_date);
CREATE INDEX IF NOT EXISTS idx_weather_records_field_id ON weather_records(field_id);
CREATE INDEX IF NOT EXISTS idx_weather_records_recorded_at ON weather_records(recorded_at);
CREATE INDEX IF NOT EXISTS idx_risk_predictions_crop_id ON risk_predictions(crop_id);
CREATE INDEX IF NOT EXISTS idx_risk_predictions_created_at ON risk_predictions(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_crop_id ON alerts(crop_id);
CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_user_crop_id ON alerts(user_crop_id);
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_reference ON feedback(feedback_type, reference_id);
"""


@contextmanager
def connection():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def init_db():
    with connection() as conn:
        conn.execute(SCHEMA_SQL)
        apply_migrations(conn)
        conn.commit()


def apply_migrations(conn, migrations_dir=None):
    """Apply each numbered SQL migration once, without replacing user data."""
    migrations_dir = Path(migrations_dir or Path(__file__).resolve().parent / "migrations")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Serialize startup migrations when multiple API workers start together.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (7281946301,))
    applied = {
        row["migration_id"]
        for row in conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    for migration in sorted(migrations_dir.glob("[0-9]*.sql")):
        if migration.stem in applied:
            continue
        conn.execute(migration.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (migration_id) VALUES (%s)",
            (migration.stem,),
        )


def save_scan(result, filename=None, user_id=None):
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO scans (filename, crop, disease, healthy, confidence, recommendations, model_status, user_id)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, created_at
            """,
            (
                filename,
                result["crop"],
                result["disease"],
                result["healthy"],
                result["confidence"],
                __import__("json").dumps(result["recommendations"]),
                result.get("model_status", "unknown"),
                user_id,
            ),
        ).fetchone()
        conn.commit()
        return row


def save_chat(question, answer, source, user_id=None):
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO chat_messages (question, answer, source, user_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (question, answer, source, user_id),
        ).fetchone()
        conn.commit()
        return row


def recent_scans(user_id, limit=20):
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM scans WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit)
        ).fetchall()


def _create_record(table, values):
    columns = list(values)
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    with connection() as conn:
        return conn.execute(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) RETURNING *",
            [values[column] for column in columns],
        ).fetchone()


def _get_record(table, record_id):
    with connection() as conn:
        return conn.execute(
            f"SELECT * FROM {table} WHERE id = %s", (record_id,)
        ).fetchone()


def _update_record(table, record_id, values, allowed_columns):
    values = {key: value for key, value in values.items() if key in allowed_columns}
    if not values:
        return _get_record(table, record_id)
    assignments = ", ".join(f"{column} = %s" for column in values)
    with connection() as conn:
        return conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = %s RETURNING *",
            [*values.values(), record_id],
        ).fetchone()


def _delete_record(table, record_id):
    with connection() as conn:
        return conn.execute(
            f"DELETE FROM {table} WHERE id = %s RETURNING id", (record_id,)
        ).fetchone()


def list_records(table, foreign_key=None, foreign_id=None):
    query = f"SELECT * FROM {table}"
    params = []
    if foreign_key is not None:
        query += f" WHERE {foreign_key} = %s"
        params.append(foreign_id)
    query += " ORDER BY id DESC"
    with connection() as conn:
        return conn.execute(query, params).fetchall()


def create_user(values):
    return _create_record("users", values)


def get_user(user_id):
    return _get_record("users", user_id)


def list_users():
    return list_records("users")


def get_user_by_email(email):
    with connection() as conn:
        return conn.execute("SELECT * FROM users WHERE lower(email) = lower(%s)", (email,)).fetchone()


def create_auth_user(values):
    return _create_record("users", values)


def update_user(user_id, values):
    return _update_record("users", user_id, values, {"name", "phone", "email", "user_type", "state", "district", "preferred_language"})


def update_farmer_profile(user_id, values):
    allowed = {"name", "state", "district", "preferred_language"}
    values = {key: value for key, value in values.items() if key in allowed}
    if not values:
        return get_user(user_id)
    assignments = ", ".join(f"{column} = %s" for column in values)
    with connection() as conn:
        return conn.execute(
            f"UPDATE users SET {assignments} WHERE id = %s RETURNING id, name, email, user_type, state, district, preferred_language, location_consent_at",
            [*values.values(), user_id],
        ).fetchone()


def set_location_consent(user_id, consent):
    with connection() as conn:
        return conn.execute(
            "UPDATE users SET location_consent_at = CASE WHEN %s THEN NOW() ELSE NULL END WHERE id = %s RETURNING location_consent_at",
            (consent, user_id),
        ).fetchone()


def save_user_location(user_id, values):
    with connection() as conn:
        return conn.execute(
            """
            INSERT INTO user_locations (user_id, latitude, longitude, location_name, accuracy)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                location_name = EXCLUDED.location_name,
                accuracy = EXCLUDED.accuracy,
                updated_at = NOW()
            RETURNING *
            """,
            (
                user_id,
                values["latitude"],
                values["longitude"],
                values.get("location_name"),
                values.get("accuracy"),
            ),
        ).fetchone()


def get_user_location(user_id):
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM user_locations WHERE user_id = %s", (user_id,)
        ).fetchone()


def delete_user_location(user_id):
    with connection() as conn:
        conn.execute("DELETE FROM user_locations WHERE user_id = %s", (user_id,))


def delete_user(user_id):
    return _delete_record("users", user_id)


def create_farm(values):
    return _create_record("farms", values)


def get_farm(farm_id):
    return _get_record("farms", farm_id)


def get_owned_farm(farm_id, user_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM farms WHERE id = %s AND user_id = %s", (farm_id, user_id)).fetchone()


def list_farms(user_id):
    return list_records("farms", "user_id", user_id)


def update_farm(farm_id, values):
    return _update_record("farms", farm_id, values, {"name", "location", "state", "district", "area_acres", "area_amount", "area_unit", "irrigation_method", "notes"})


def delete_farm(farm_id):
    return _delete_record("farms", farm_id)


def create_field(values):
    return _create_record("fields", values)


def get_field(field_id):
    return _get_record("fields", field_id)


def get_owned_field(field_id, user_id):
    with connection() as conn:
        return conn.execute(
            "SELECT fields.* FROM fields JOIN farms ON farms.id = fields.farm_id WHERE fields.id = %s AND farms.user_id = %s",
            (field_id, user_id),
        ).fetchone()


def list_fields(farm_id):
    return list_records("fields", "farm_id", farm_id)


def update_field(field_id, values):
    return _update_record("fields", field_id, values, {"name", "area_acres", "soil_type", "irrigation_type", "notes"})


def delete_field(field_id):
    return _delete_record("fields", field_id)


def create_crop(values):
    return _create_record("crops", values)


def get_crop(crop_id):
    return _get_record("crops", crop_id)


def get_owned_crop(crop_id, user_id):
    with connection() as conn:
        return conn.execute(
            "SELECT crops.* FROM crops JOIN fields ON fields.id = crops.field_id JOIN farms ON farms.id = fields.farm_id WHERE crops.id = %s AND farms.user_id = %s",
            (crop_id, user_id),
        ).fetchone()


def list_crops(field_id):
    return list_records("crops", "field_id", field_id)


def update_crop(crop_id, values):
    return _update_record("crops", crop_id, values, {"crop_name", "variety", "season", "sowing_date", "expected_harvest_date", "current_stage", "status", "notes"})


def delete_crop(crop_id):
    return _delete_record("crops", crop_id)


def create_soil_record(values):
    return _create_record("soil_records", values)


def list_soil_records(field_id):
    return list_records("soil_records", "field_id", field_id)


def create_crop_event(values):
    return _create_record("crop_events", values)


def list_crop_events(crop_id):
    return list_records("crop_events", "crop_id", crop_id)


def create_weather_record(values):
    return _create_record("weather_records", values)


def list_weather_records(field_id):
    return list_records("weather_records", "field_id", field_id)


def create_risk_prediction(values):
    values = dict(values)
    reasons = values.get("reasons", "[]")
    if not isinstance(reasons, str):
        import json

        reasons = json.dumps(reasons)
    with connection() as conn:
        columns = [key for key in values if key != "reasons"]
        column_sql = ", ".join([*columns, "reasons"])
        placeholders = ", ".join(["%s"] * len(columns) + ["%s::jsonb"])
        return conn.execute(
            f"INSERT INTO risk_predictions ({column_sql}) VALUES ({placeholders}) RETURNING *",
            [*[values[column] for column in columns], reasons],
        ).fetchone()


def list_risk_predictions(crop_id):
    return list_records("risk_predictions", "crop_id", crop_id)


def create_alert(values):
    return _create_record("alerts", values)


def find_recent_alert(crop_id, alert_type, title):
    with connection() as conn:
        return conn.execute(
            """
            SELECT * FROM alerts
            WHERE crop_id = %s
              AND alert_type = %s
              AND title = %s
              AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (crop_id, alert_type, title),
        ).fetchone()


def find_user_crop_alert_event(user_crop_id, title):
    """Find an alert already created for this saved-crop forecast event."""
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM alerts WHERE user_crop_id = %s AND title = %s ORDER BY created_at DESC LIMIT 1",
            (user_crop_id, title),
        ).fetchone()


def list_alerts(crop_id=None):
    if crop_id is None:
        with connection() as conn:
            return conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    return list_records("alerts", "crop_id", crop_id)


def list_user_crop_alerts(crop_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM alerts WHERE user_crop_id = %s ORDER BY created_at DESC", (crop_id,)).fetchall()


def list_user_alerts(user_id):
    with connection() as conn:
        return conn.execute(
            """
            SELECT DISTINCT alerts.* FROM alerts
            LEFT JOIN crops ON crops.id = alerts.crop_id
            LEFT JOIN fields ON fields.id = crops.field_id
            LEFT JOIN farms ON farms.id = fields.farm_id
            LEFT JOIN user_crops ON user_crops.id = alerts.user_crop_id
            WHERE farms.user_id = %s OR user_crops.user_id = %s
            ORDER BY alerts.created_at DESC
            """,
            (user_id, user_id),
        ).fetchall()


def mark_alert_read(alert_id):
    with connection() as conn:
        return conn.execute(
            "UPDATE alerts SET is_read = TRUE WHERE id = %s RETURNING *",
            (alert_id,),
        ).fetchone()


def mark_alert_read_owned(alert_id, user_id):
    with connection() as conn:
        return conn.execute(
            """
            UPDATE alerts SET is_read = TRUE
            WHERE id = %s AND (
                crop_id IN (SELECT crops.id FROM crops JOIN fields ON fields.id = crops.field_id JOIN farms ON farms.id = fields.farm_id WHERE farms.user_id = %s)
                OR user_crop_id IN (SELECT id FROM user_crops WHERE user_id = %s)
            ) RETURNING *
            """,
            (alert_id, user_id, user_id),
        ).fetchone()


def create_feedback(values):
    return _create_record("feedback", values)


def list_feedback():
    return list_records("feedback")


def summary_counts():
    tables = ("users", "farms", "fields", "crops", "user_crops", "scans", "risk_predictions", "alerts", "feedback")
    with connection() as conn:
        return {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in tables}


def create_user_crop(values):
    return _create_record("user_crops", values)


def get_user_crop(crop_id):
    return _get_record("user_crops", crop_id)


def get_owned_user_crop(crop_id, user_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM user_crops WHERE id = %s AND user_id = %s", (crop_id, user_id)).fetchone()


def list_user_crops(user_id=None):
    if user_id is None:
        return []
    return list_records("user_crops", "user_id", user_id)


def update_user_crop(crop_id, values):
    return _update_record(crop_id and "user_crops", crop_id, values, {"crop_name", "variety", "latitude", "longitude", "city", "district", "state", "country", "planting_date", "growth_stage", "soil_type", "drainage_condition", "irrigation_availability", "mode", "updated_at"})


def save_weather_snapshot(crop_id, payload):
    import json
    with connection() as conn:
        return conn.execute("INSERT INTO weather_snapshots (crop_id, payload) VALUES (%s, %s::jsonb) RETURNING *", (crop_id, json.dumps(payload))).fetchone()


def save_crop_risk(crop_id, result):
    import json
    with connection() as conn:
        return conn.execute("INSERT INTO crop_risks (crop_id, risk_level, risk_score, result, expires_at) VALUES (%s, %s, %s, %s::jsonb, NOW() + INTERVAL '6 hours') RETURNING *", (crop_id, result["overall_risk"], result["risk_score"], json.dumps(result))).fetchone()


def latest_crop_risk(crop_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM crop_risks WHERE crop_id = %s ORDER BY created_at DESC LIMIT 1", (crop_id,)).fetchone()


def list_crop_risks(crop_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM crop_risks WHERE crop_id = %s ORDER BY created_at DESC", (crop_id,)).fetchall()
