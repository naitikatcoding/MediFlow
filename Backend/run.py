import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure the Backend directory is on sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

root_env = Path(backend_dir).parent / ".env"
if root_env.is_file():
    load_dotenv(root_env, override=False)

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  MediFlow — Backend API Starting")
    print("  Local URL:    http://127.0.0.1:8000")
    print("  API Docs:     http://127.0.0.1:8000/docs")
    print("=" * 60 + "\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
