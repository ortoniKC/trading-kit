"""Tiny .env reader and writer, so the kit needs no extra dependency."""
import os

PATH = ".env"

def load_env(path: str = PATH) -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

def set_key(key: str, value: str, path: str = PATH) -> None:
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    out, found = [], False
    for line in lines:
        if "=" in line and line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)
    os.environ[key] = value
