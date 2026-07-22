import os
import sys
from pathlib import Path

# The app's modules (api, graph, db, …) are top-level inside src/ — put src/ on
# sys.path so the run path matches the test path (harness/patterns/phases.md gate 3).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8001")), reload=False)
