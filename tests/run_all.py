"""
Run every standalone Mairon regression test in tests/test_*.py.

Mairon's regression files are plain Python scripts, so this runner executes
each test in its own process using the same Python interpreter/virtual
environment that launched this script.

Usage from the project root:

    python tests/run_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent


def discover_tests() -> list[Path]:
    return sorted(
        path
        for path in TESTS_DIR.glob("test_*.py")
        if path.is_file()
    )


def run() -> int:
    tests = discover_tests()

    if not tests:
        print("No test_*.py files found.")
        return 1

    print(
        f"Running {len(tests)} Mairon regression tests "
        f"with {sys.executable}\n"
    )

    passed: list[str] = []
    failed: list[str] = []

    for index, test_path in enumerate(tests, start=1):
        relative = test_path.relative_to(PROJECT_ROOT)

        print("=" * 72)
        print(f"[{index}/{len(tests)}] {relative}")
        print("=" * 72)

        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(PROJECT_ROOT),
        )

        print()

        if result.returncode == 0:
            passed.append(test_path.name)
            continue

        failed.append(test_path.name)

        print(f"FAILED: {relative}")
        print(
            "\nStopping at the first failure so the "
            "original traceback stays easy to find."
        )
        break

    print()
    print("=" * 72)
    print("MAIRON REGRESSION SUMMARY")
    print("=" * 72)
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")
    print(f"Total discovered: {len(tests)}")

    if failed:
        print(f"\nFirst failure: {failed[0]}")
        return 1

    print("\nALL MAIRON REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
