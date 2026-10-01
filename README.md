# FileDrop

A tiny web app for moving a file between your own browser sessions — e.g.
upload from your laptop, download on your phone — without the file
persisting on the server once it's been picked up.

Packaged as a [YunoHost](https://yunohost.org) app (`filedrop_ynh`), meant
to be installed on your own YunoHost server.

## How it works

- There's no login page or password of its own. The app sits behind
  YunoHost's nginx + SSOwat, which already enforces login and forwards the
  authenticated username to the backend as the `Ynh-User` HTTP header (see
  `conf/nginx.conf`'s `include proxy_params_with_auth;`).
- Every uploaded file is tagged with the uploader's username. The file list
  endpoint only ever returns the current user's own files — so as long as
  you're logged into YunoHost as the same account in both browsers, a file
  you upload on one shows up as "available to download" on the other, and
  nobody else can see or fetch it.
- The browser polls `/api/files` every few seconds, so a newly uploaded
  file shows up on the other device within a few seconds without a manual
  refresh.
- Downloading is destructive: the backend atomically marks the file
  "claimed" before streaming it, and deletes the blob + database row the
  moment the HTTP response finishes sending (success or client-abort —
  either way the file is considered consumed). Two simultaneous download
  clicks for the same file can't both succeed.
- As a safety net for files that are uploaded but never downloaded, a
  background thread deletes anything older than `FILEDROP_TTL_HOURS`
  (default 24h).

## Project layout

```
manifest.toml           YunoHost app manifest (packaging_format = 2)
scripts/                YunoHost lifecycle scripts (install/remove/upgrade/...)
conf/nginx.conf          nginx reverse-proxy + SSO template
conf/systemd.service     systemd unit template (runs gunicorn)
sources/filedrop/        the actual Flask app (server.py + static/)
```

## Local development (no YunoHost required)

The app trusts an `Ynh-User` header for identity. Outside of YunoHost there's
no SSOwat to set it, so a `FILEDROP_DEV_USER` env var stands in for it:

```bash
cd sources/filedrop
python -m venv venv
venv/bin/pip install -r requirements.txt
FILEDROP_DEV_USER=alice FILEDROP_DATA_DIR=./data venv/bin/python server.py
```

Then open http://127.0.0.1:6500. To simulate "two logged-in browsers", open
a second tab/window as the same `FILEDROP_DEV_USER` — e.g. run a second
instance on another port with the same `FILEDROP_DATA_DIR`, or just use two
browser tabs against the one running instance, since the dev user is fixed
per server process rather than per real login.

## Installing on YunoHost

From the server (or via the YunoHost admin webadmin, "install from URL/path"):

```bash
sudo yunohost app install /path/to/filedrop_ynh
# or, once pushed to a git remote:
sudo yunohost app install https://your-git-host/you/filedrop_ynh
```

You'll be asked for a domain, a URL path (default `/filedrop`), and which
user group is allowed to use it (default: all users on the server).

### Caveats to check before relying on this in production

- This manifest/these scripts were written against the documented
  packaging_format = 2 conventions and a real `example_ynh` skeleton, but
  weren't tested against a live YunoHost instance (none was available in
  this session). Helper names (`ynh_config_add_*`) and manifest resource
  syntax do shift between YunoHost core versions — if `yunohost app install`
  errors out on a helper name, check `yunohost --version` against
  https://doc.yunohost.org/en/packaging_apps_helpers_reference for the
  current equivalent.
- `client_max_body_size` in `conf/nginx.conf` and `FILEDROP_MAX_UPLOAD_MB`
  in `conf/systemd.service` are both hardcoded to match (2 GB) — if you
  change one, change the other.
- Uninstalling the app deletes its data directory (any not-yet-downloaded
  files) along with it.
