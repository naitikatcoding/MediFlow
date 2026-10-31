"""MediFlow Development Launcher.
Usage:
  python scripts/dev.py backend    # Run FastAPI backend only
  python scripts/dev.py frontend   # Run Next.js frontend only
  python scripts/dev.py all        # Run both concurrently
"""
import sys
import subprocess
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "Backend"
FRONTEND_DIR = ROOT / "Frontend"


def run_backend():
    print("--> Starting MediFlow FastAPI Backend on http://127.0.0.1:8000 ...")
    python_bin = sys.executable
    venv_py = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        python_bin = str(venv_py)
    subprocess.run([python_bin, "run.py"], cwd=str(BACKEND_DIR))


def run_frontend():
    print("--> Starting MediFlow Next.js Frontend on http://localhost:3000 ...")
    shell = os.name == "nt"
    subprocess.run(["npm", "run", "dev"], cwd=str(FRONTEND_DIR), shell=shell)


def run_all():
    print("--> Launching MediFlow Full Stack (Backend + Frontend)...")
    python_bin = sys.executable
    venv_py = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        python_bin = str(venv_py)

    shell = os.name == "nt"
    backend_proc = subprocess.Popen([python_bin, "run.py"], cwd=str(BACKEND_DIR))
    frontend_proc = subprocess.Popen(["npm", "run", "dev"], cwd=str(FRONTEND_DIR), shell=shell)

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\n--> Shutting down services...")
        backend_proc.terminate()
        frontend_proc.terminate()


if __name__ == "__main__":
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if target == "backend":
        run_backend()
    elif target == "frontend":
        run_frontend()
    elif target == "all":
        run_all()
    else:
        print("Invalid target. Use 'backend', 'frontend', or 'all'.")
        sys.exit(1)
