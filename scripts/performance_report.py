"""Export sanitized timing totals for a branch/task from the execution store."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from execution_store import ExecutionStore
from performance import summarize

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("task")
    args = parser.parse_args()
    print(json.dumps(summarize(ExecutionStore(args.database).list("operation", args.task)), indent=2))
