#!/usr/bin/env python3
"""Check the skill runtime; optionally initialize an isolated common-table environment."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


PROBE = r'''
import csv, io, json, re, sys
from importlib.metadata import version
result = {"python": sys.executable, "python_version": sys.version.split()[0], "packages": {}, "checks": {}, "ready": False}
try:
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required for this runtime profile")
    rows = list(csv.DictReader(io.StringIO('id,value\n1,"two,parts"\n')))
    assert rows == [{"id": "1", "value": "two,parts"}]
    result["checks"]["csv"] = "passed"
    if sys.argv[1] == "tabular":
        import pandas as pd
        import openpyxl
        for package, minimum in [("pandas", (2, 3, 3)), ("openpyxl", (3, 1, 5))]:
            installed = version(package)
            result["packages"][package] = installed
            match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:$|\.post\d+$)", installed)
            if not match or not minimum <= tuple(map(int, match.groups())) < (4, 0, 0):
                raise RuntimeError(package + " does not satisfy this profile: " + installed)
        result["packages"]["numpy"] = version("numpy")
        content = io.BytesIO()
        workbook = openpyxl.Workbook()
        workbook.active.append(["id", "value"])
        workbook.active.append([1, "sample"])
        workbook.save(content)
        workbook.close()
        content.seek(0)
        reopened = openpyxl.load_workbook(content, read_only=True, data_only=True)
        assert list(reopened.active.values) == [("id", "value"), (1, "sample")]
        reopened.close()
        content.seek(0)
        frame = pd.read_excel(content, engine="openpyxl")
        assert frame.to_dict("records") == [{"id": 1, "value": "sample"}]
        result["checks"]["xlsx_openpyxl_and_pandas"] = "passed"
    result["ready"] = True
except Exception as error:
    result["error"] = type(error).__name__ + ": " + str(error)
print(json.dumps(result, ensure_ascii=True))
'''


def probe(python, profile):
    try:
        completed = subprocess.run(
            [str(python), "-B", "-X", "utf8", "-c", PROBE, profile],
            capture_output=True, text=True, encoding="utf-8", timeout=45, check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Python probe failed")
        return json.loads(completed.stdout)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        return {"python": str(python), "ready": False, "error": str(error)}


def save_receipt(state_dir, result, profile):
    state_dir.mkdir(parents=True, exist_ok=True)
    result = dict(result, profile=profile, checked_at=datetime.now(timezone.utc).isoformat())
    result["page_display_and_callback"] = "not_tested_by_environment_setup"
    receipt = state_dir / "runtime.json"
    temporary = state_dir / "runtime.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(receipt)
    # stdout encoding is host-dependent; a non-UTF-8 console must not turn a written receipt into a false failure
    stream_encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    def console(text):
        return text.encode(stream_encoding, "replace").decode(stream_encoding, "replace")
    print(console(json.dumps(result, ensure_ascii=False, indent=2)), flush=True)
    print(console("Runtime receipt: " + str(receipt)), flush=True)
    return 0 if result.get("ready") else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "tabular"), default="tabular")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".cache" / "data-to-value")
    parser.add_argument("--install", action="store_true", help="Install missing table dependencies into the skill's isolated environment")
    args = parser.parse_args()
    state_dir = args.state_dir.expanduser().resolve()
    environment = state_dir / "venv"
    environment_python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    candidates = []
    receipt = state_dir / "runtime.json"
    if receipt.exists():
        try:
            previous = json.loads(receipt.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and previous.get("ready") and isinstance(previous.get("python"), str):
                candidates.append(Path(previous["python"]))
        except (OSError, ValueError):
            pass
    candidates += [environment_python, Path(sys.executable)]
    attempted = set()
    result = {"ready": False, "error": "No working Python runtime found"}
    try:
        for python in candidates:
            if str(python) in attempted or not python.is_file():
                continue
            attempted.add(str(python))
            result = probe(python, args.profile)
            if result.get("ready"):
                return save_receipt(state_dir, result, args.profile)
        if args.install and args.profile == "tabular":
            print("Preparing isolated table environment: " + str(environment), flush=True)
            requirements = Path(__file__).resolve().parent.parent / "requirements-tabular.txt"
            try:
                if not environment_python.is_file():
                    venv.EnvBuilder(with_pip=True).create(environment)
                subprocess.run(
                    [str(environment_python), "-m", "pip", "--disable-pip-version-check", "install",
                     "--only-binary=:all:", "--retries", "1", "--timeout", "30", "-r", str(requirements)],
                    check=True, timeout=300,
                )
                result = probe(environment_python, args.profile)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                result = {"python": str(environment_python), "ready": False, "error": "Dependency initialization failed: " + str(error)}
        return save_receipt(state_dir, result, args.profile)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, "Environment preparation failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
