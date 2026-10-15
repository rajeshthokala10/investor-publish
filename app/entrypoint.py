"""Container entrypoint: prepare the Railway volume as root, then drop to the unprivileged 'web' user."""
import os
import pwd
import sys

data = os.path.dirname(os.environ.get("APP_DB", "/data/app.db")) or "/data"
user = pwd.getpwnam("web")
if os.getuid() == 0:
    os.makedirs(data, exist_ok=True)
    os.chown(data, user.pw_uid, user.pw_gid)
    for name in os.listdir(data):
        os.chown(os.path.join(data, name), user.pw_uid, user.pw_gid)
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    os.environ["HOME"] = user.pw_dir
port = os.environ.get("PORT", "8080")
os.execvp("uvicorn", ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", port,
                      "--proxy-headers", "--forwarded-allow-ips", "*", *sys.argv[1:]])
