"""Run every offline project check in one go: pytest plus the Node contract/unit tests.

Usage (from the repo root, inside the project environment):
    python scripts/run_checks.py            # all checks
    python scripts/run_checks.py --no-node  # Python only (e.g. no Node.js installed)
    python scripts/run_checks.py -- -k presets   # extra args after -- go to pytest

Postgres-backed tests skip automatically when kronos_research is unreachable.
Model-weight checks stay in scripts/verify_setup.py because they need local weights.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_TESTS = sorted((ROOT / "tests").glob("*.cjs")) + sorted((ROOT / "browser" / "chrome-bridge" / "tests").glob("*.test.cjs"))


def run(label, command):
    print(f"\n=== {label}", flush=True)
    code = subprocess.call(command, cwd=ROOT)
    print(f"--- {label}: {'ok' if code == 0 else f'FAILED ({code})'}", flush=True)
    return code == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-node", action="store_true", help="Skip the Node.js tests.")
    parser.add_argument("pytest_args", nargs="*", help="Extra pytest arguments (put them after --).")
    args = parser.parse_args()

    results = {"pytest": run("pytest", [sys.executable, "-m", "pytest", "-q", "-rs", *args.pytest_args])}
    if not args.no_node:
        node = shutil.which("node")
        if node is None:
            print("\nNode.js not found; JS tests cannot run. Install Node.js or pass --no-node to skip them.")
            results["node"] = False
        else:
            for test in NODE_TESTS:
                results[test.relative_to(ROOT).as_posix()] = run(test.name, [node, str(test)])

    failed = [name for name, ok in results.items() if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} check groups passed." + (f" Failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
