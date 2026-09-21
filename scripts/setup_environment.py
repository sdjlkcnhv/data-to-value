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


from console_utils import configure_console


def probe(python, profile, language="eng"):
    try:
        completed = subprocess.run(
            [str(python), "-B", "-X", "utf8", str(Path(__file__).with_name("runtime_probe.py")), profile, language],
            capture_output=True, text=True, encoding="utf-8", timeout=180, check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Python probe failed")
        return json.loads(completed.stdout)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        return {"python": str(python), "ready": False, "error": str(error)}


def save_receipt(state_dir, result, profile):
    state_dir.mkdir(parents=True, exist_ok=True)
    result = dict(result, profile=profile, skill_version="0.2.0", checked_at=datetime.now(timezone.utc).isoformat())
    result["page_display_and_callback"] = "not_tested_by_environment_setup"
    receipt = state_dir / ("runtime-" + profile + ".json")
    temporary = receipt.with_suffix(".json.tmp")
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
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "tabular", "common", "ocr"), default="common")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".cache" / "data-to-value")
    parser.add_argument("--install", action="store_true", help="Install missing table dependencies into the skill's isolated environment")
    parser.add_argument("--language", default="eng", help="OCR languages, e.g. eng+chi_sim")
    args = parser.parse_args()
    state_dir = args.state_dir.expanduser().resolve()
    environment = state_dir / "venv"
    environment_python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    candidates = []
    receipt = state_dir / ("runtime-" + args.profile + ".json")
    if not receipt.exists():
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
        state_dir.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.TemporaryFile(dir=state_dir):
            pass
        for python in candidates:
            if str(python) in attempted or not python.is_file():
                continue
            attempted.add(str(python))
            result = probe(python, args.profile, args.language)
            if result.get("ready"):
                return save_receipt(state_dir, result, args.profile)
        if args.install and args.profile != "core":
            print("Preparing isolated table environment: " + str(environment), flush=True)
            requirements = Path(__file__).resolve().parent.parent / ("requirements-" + args.profile + ".txt")
            try:
                if not environment_python.is_file():
                    venv.EnvBuilder(with_pip=True).create(environment)
                subprocess.run(
                    [str(environment_python), "-m", "pip", "--disable-pip-version-check", "install",
                     "--only-binary=:all:", "--retries", "1", "--timeout", "30", "-r", str(requirements)],
                    check=True, timeout=600,
                )
                result = probe(environment_python, args.profile, args.language)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                result = {"python": str(environment_python), "ready": False, "error": "Dependency initialization failed: " + str(error)}
        return save_receipt(state_dir, result, args.profile)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, "Environment preparation failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
