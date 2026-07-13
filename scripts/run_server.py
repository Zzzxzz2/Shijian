"""Start the shijian-v2 backend server for E2E testing."""
import sys, os

# Add <project_root>/backend/ to sys.path so database, main, models etc. are importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "backend"))

import uvicorn
from main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
