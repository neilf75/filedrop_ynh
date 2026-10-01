"""
FileDrop backend.

Identity model: this app has no login of its own. It trusts the
YunoHost/SSOwat reverse proxy to authenticate the user and forward their
username in the `Ynh-User` header (see conf/nginx.conf's
`include proxy_params_with_auth;`). Every file is scoped to the uploading
user's username, so a user only ever sees files they themselves uploaded,
regardless of which browser/device they're logged in on.

For local development without YunoHost in front, set FILEDROP_DEV_USER to
fake the header.
"""

import mimetypes
import os
import sqlite3
import time
import uuid
import threading
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, abort, g, jsonify, request, stream_with_context

DATA_DIR = Path(os.environ.get("FILEDROP_DATA_DIR", "./data")).resolve()
BLOB_DIR = DATA_DIR / "blobs"
DB_PATH = DATA_DIR / "filedrop.db"
MAX_UPLOAD_MB = int(os.environ.get("FILEDROP_MAX_UPLOAD_MB", "2048"))
TTL_HOURS = float(os.environ.get("FILEDROP_TTL_HOURS", "24"))
DEV_USER = os.environ.get("FILEDROP_DEV_USER")
CLEANUP_INTERVAL_SECONDS = 600

BLOB_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            filename TEXT NOT NULL,
            size INTEGER NOT NULL,
            uploaded_at REAL NOT NULL,
            claimed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(_exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def current_user():
    user = request.headers.get("Ynh-User") or request.headers.get("X-Forwarded-User") or DEV_USER
    if not user:
        abort(401, description="No authenticated user (missing Ynh-User header)")
    return user


@app.get("/api/me")
def me():
    user = current_user()
    display_name = request.headers.get("Ynh-User-Fullname") or user
    return jsonify(username=user, display_name=display_name)


@app.get("/api/files")
def list_files():
    user = current_user()
    rows = get_db().execute(
        "SELECT id, filename, size, uploaded_at FROM files "
        "WHERE owner = ? AND claimed = 0 ORDER BY uploaded_at DESC",
        (user,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/upload")
def upload():
    user = current_user()
    f = request.files.get("file")
    if f is None or f.filename == "":
        abort(400, description="No file provided")

    file_id = uuid.uuid4().hex
    dest = BLOB_DIR / file_id
    f.save(dest)
    size = dest.stat().st_size

    db = get_db()
    db.execute(
        "INSERT INTO files (id, owner, filename, size, uploaded_at, claimed) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        (file_id, user, f.filename, size, time.time()),
    )
    db.commit()
    return jsonify(id=file_id, filename=f.filename, size=size), 201


def content_disposition(filename):
    safe = filename.replace("\r", "").replace("\n", "")
    ascii_fallback = safe.encode("ascii", "replace").decode("ascii").replace('"', "")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe)}"


@app.get("/api/files/<file_id>/download")
def download(file_id):
    user = current_user()
    db = get_db()

    # Atomically claim the row so two near-simultaneous downloads (e.g. the
    # same user double-clicking on two devices) can't both serve/delete it.
    cur = db.execute(
        "UPDATE files SET claimed = 1 WHERE id = ? AND owner = ? AND claimed = 0",
        (file_id, user),
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)

    row = db.execute("SELECT filename, size FROM files WHERE id = ?", (file_id,)).fetchone()
    blob_path = BLOB_DIR / file_id

    def generate():
        try:
            with open(blob_path, "rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Runs whether the download finished normally or the client
            # disconnected partway through (WSGI closes the generator
            # either way), so the blob never outlives the response.
            blob_path.unlink(missing_ok=True)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()
            conn.close()

    headers = {
        "Content-Disposition": content_disposition(row["filename"]),
        "Content-Length": str(row["size"]),
        "Content-Type": mimetypes.guess_type(row["filename"])[0] or "application/octet-stream",
    }
    return Response(stream_with_context(generate()), headers=headers)


@app.delete("/api/files/<file_id>")
def delete_file(file_id):
    user = current_user()
    db = get_db()
    row = db.execute("SELECT id FROM files WHERE id = ? AND owner = ?", (file_id, user)).fetchone()
    if row is None:
        abort(404)
    db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    db.commit()
    (BLOB_DIR / file_id).unlink(missing_ok=True)
    return "", 204


@app.get("/")
def index():
    return app.send_static_file("index.html")


def cleanup_expired_loop():
    """Safety net for files that are uploaded but never downloaded."""
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cutoff = time.time() - TTL_HOURS * 3600
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT id FROM files WHERE uploaded_at < ?", (cutoff,)).fetchall()
        for (file_id,) in rows:
            (BLOB_DIR / file_id).unlink(missing_ok=True)
        conn.execute("DELETE FROM files WHERE uploaded_at < ?", (cutoff,))
        conn.commit()
        conn.close()


init_db()
threading.Thread(target=cleanup_expired_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "6500")), debug=bool(os.environ.get("FLASK_DEBUG")))
