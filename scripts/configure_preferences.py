#!/usr/bin/env python3
"""Create an offline preference form; optionally collect confirmation on localhost."""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import secrets
import time
import webbrowser
from console_utils import configure_console


PROFILES = {
    "academic": [
        ("novelty", "创新度", 30, "与已有研究相比，这个问题或方法有多少新内容。"),
        ("significance", "研究意义", 25, "研究结果能否帮助理解或解决重要问题。"),
        ("data_fit", "数据适配", 20, "现有数据是否包含回答问题所需的信息。"),
        ("feasibility", "实施可行性", 15, "现有时间、人员和计算资源是否足够完成研究。"),
        ("validation", "验证设计", 10, "能否通过对照和实验，检验研究结论是否成立。"),
    ],
    "business": [
        ("value", "潜在净价值", 30, "扣除实施和运营成本后，是否仍有收益或决策改进价值。"),
        ("time", "见效时间", 20, "需要多久才能得到验证结果或达到约定的业务目标。"),
        ("cost", "执行成本", 20, "需要多少人力、资金和后续维护投入。"),
        ("action", "落地条件", 15, "是否有人使用、有人负责，并具备执行与维护条件。"),
        ("measure", "效果可测量性", 15, "能否记录结果，并判断方案是否比现有做法更有效。"),
    ],
}


def validate_preferences(data, expected_mode=None, dimension_ids=None):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Preference data must use schema_version 1")
    mode = data.get("mode")
    if not isinstance(mode, str) or mode not in PROFILES or (expected_mode is not None and mode != expected_mode):
        raise ValueError("Preference mode does not match this task")
    if data.get("confirmed") is not True:
        raise ValueError("Preferences have not been explicitly confirmed")
    expected_ids = set(dimension_ids if dimension_ids is not None else (row[0] for row in PROFILES[mode]))
    weights = data.get("weights")
    if not isinstance(weights, dict) or set(weights) != expected_ids:
        raise ValueError("Preference dimensions must exactly match the report")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Preference weights must be finite nonnegative numbers")
    if not math.isfinite(sum(weights.values())) or sum(weights.values()) <= 0:
        raise ValueError("Total preference weight must be finite and positive")
    constraints = data.get("constraints", "")
    if not isinstance(constraints, str) or len(constraints) > 4000:
        raise ValueError("Constraints must be text of at most 4000 characters")
    return data


HTML = (Path(__file__).resolve().parents[1] / "assets" / "startup.html").read_text(encoding="utf-8")


def render(mode=None, submit_path=None):
    if mode is not None and mode not in PROFILES:
        raise ValueError("Unknown mode")
    config = {
        "mode": mode,
        "profiles": {key: [dict(zip(("id", "label", "weight", "description"), row)) for row in rows] for key, rows in PROFILES.items()},
        "submit_path": submit_path,
    }
    return HTML.replace("__CONFIG__", json.dumps(config, ensure_ascii=True).replace("<", r"\u003c"))


def request_browser(url):
    try:
        requested = webbrowser.open(url, new=2)
    except (OSError, webbrowser.Error):
        requested = False
    print(("Browser open requested: " if requested else "Open or preview this page: ") + url, flush=True)


def collect(mode, result_path, timeout, open_browser):
    token_path = "/" + secrets.token_urlsafe(24) + "/"
    state = {"saved": False}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(3)
            super().setup()

        def log_message(self, *_args):
            pass

        def respond(self, status, body, content_type="application/json"):
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path != token_path:
                self.respond(404, '{"error":"Not found"}')
                return
            self.respond(200, render(mode, token_path + "confirm"), "text/html")

        def do_POST(self):
            if self.path != token_path + "confirm" or self.headers.get("Origin") != origin:
                self.respond(403, '{"error":"Invalid confirmation origin or path"}')
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, '{"error":"JSON required"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768:
                    raise ValueError("Invalid request size")
                preferences = validate_preferences(json.loads(self.rfile.read(length)), expected_mode=None)
            except (ValueError, OSError) as error:
                self.respond(400, json.dumps({"error": str(error)}))
                return
            receipt = {
                "schema_version": 1, "mode": preferences["mode"], "weights": preferences["weights"],
                "constraints": preferences.get("constraints", ""), "confirmed": True,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "source": "local_interactive_confirmation",
            }
            try:
                with result_path.open("x", encoding="utf-8") as handle:
                    json.dump(receipt, handle, ensure_ascii=False, allow_nan=False, indent=2)
            except OSError as error:
                self.respond(500, json.dumps({"error": str(error)}))
                return
            state["saved"] = True
            self.respond(200, '{"saved":true}')

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        origin = "http://127.0.0.1:" + str(server.server_port)
        url = origin + token_path
        server.timeout = 0.5
        print("Preference page: " + url, flush=True)
        print("Waiting for explicit confirmation; result: " + str(result_path), flush=True)
        if open_browser:
            request_browser(url)
        deadline = time.monotonic() + timeout
        while not state["saved"] and time.monotonic() < deadline:
            server.handle_request()
    if state["saved"]:
        print("Confirmed preferences: " + str(result_path), flush=True)
        return 0
    print("No preferences confirmed. Continue waiting in the conversation; do not assume defaults.", flush=True)
    return 3


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=PROFILES, help="Only preselect a mode already explicitly chosen by the user")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, help="Collect confirmation locally and save JSON here")
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--timeout", type=int, default=600, help="Local confirmation timeout in seconds (1-3600)")
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 3600:
            raise ValueError("Timeout must be between 1 and 3600 seconds")
        if args.result:
            if args.result.resolve() == args.output.resolve():
                raise ValueError("HTML and confirmation output paths must differ")
            if args.result.exists():
                raise ValueError("Confirmation file already exists; reuse it or choose a new path")
            args.result.parent.mkdir(parents=True, exist_ok=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(args.mode), encoding="utf-8")
        print("Generated: " + str(args.output.resolve()), flush=True)
        if args.result:
            return collect(args.mode, args.result.resolve(), args.timeout, args.open_browser)
        if args.open_browser:
            request_browser(args.output.resolve().as_uri())
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, "Error: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
