#!/usr/bin/env python3

import hashlib
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REQ_FILE = BASE_DIR / "requirements.txt"
HASH_FILE = BASE_DIR / ".requirements.sha256"
VENV_DIR = BASE_DIR / ".venv"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


# def git_pull() -> bool:
#     """
#     Returns True if git pulled new changes, False otherwise.
#     """
#     before = subprocess.check_output(
#         ["git", "rev-parse", "HEAD"], cwd=BASE_DIR
#     ).strip()

#     run(["git", "fetch"])
#     run(["git", "pull"])

#     after = subprocess.check_output(
#         ["git", "rev-parse", "HEAD"], cwd=BASE_DIR
#     ).strip()

#     return before != after


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_venv() -> Path:
    if not VENV_DIR.exists():
        print("[INFO] Creating virtual environment")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    return VENV_DIR / "bin" / "pip"


def requirements_changed() -> bool:
    current_hash = sha256(REQ_FILE)

    if not HASH_FILE.exists():
        HASH_FILE.write_text(current_hash)
        return True

    stored_hash = HASH_FILE.read_text().strip()
    if stored_hash != current_hash:
        HASH_FILE.write_text(current_hash)
        return True

    return False


def install_requirements(pip: Path) -> None:
    print("[INFO] Installing dependencies")
    run([str(pip), "install", "--upgrade", "pip"])
    run([str(pip), "install", "-r", str(REQ_FILE)])


def main() -> None:
    print("[INFO] Starting update")

    # changed = git_pull()
    # if not changed:
    #     print("[INFO] Git unchanged")

    if not REQ_FILE.exists():
        print("[WARN] requirements.txt not found")
        return

    if requirements_changed():
        pip = ensure_venv()
        install_requirements(pip)
        print("[INFO] Dependencies updated")
    else:
        print("[INFO] requirements.txt unchanged")

    print("[INFO] Update complete")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {e}", file=sys.stderr)
        sys.exit(1)