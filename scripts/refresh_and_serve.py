#!/usr/bin/env python3
"""Refresh the local STMA dashboard snapshot and start its web server."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from build_dashboard_data import build_snapshot
import json


def default_db_path(dashboard_dir: Path) -> Path:
    onedrive_db = Path(r"E:\Onedrive_TeerapatCh\OneDrive\MMK\Quant\Sentiment-Analysis\WSJ\Daily\Database\sentiment.db")
    if onedrive_db.exists():
        return onedrive_db
    return dashboard_dir.parents[1] / "data" / "sentiment.db"


def main() -> int:
    dashboard_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=default_db_path(dashboard_dir))
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot(args.db)
    output = dashboard_dir / "public" / "data" / "dashboard.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    if snapshot["meta"]["dataset_status"] != "ok":
        print("Dataset validation returned a warning; dashboard was not started.", file=sys.stderr)
        return 1

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    browser_host = "localhost" if args.host == "0.0.0.0" else args.host
    url = f"http://{browser_host}:{args.port}"
    print(f"STMA Quant Dashboard: {url}")
    command = [npm, "run", "dev", "--", "--hostname", args.host, "--port", str(args.port)]
    server = subprocess.Popen(command, cwd=dashboard_dir)
    try:
        import socket
        deadline = time.time() + 20.0
        ready = False
        while time.time() < deadline:
            if server.poll() is not None:
                return server.returncode or 1
            try:
                with socket.create_connection((browser_host, args.port), timeout=0.5):
                    ready = True
                    break
            except OSError:
                time.sleep(0.3)
        if not args.no_browser and ready:
            import webbrowser

            webbrowser.open(url)
        last_mtime = args.db.resolve().stat().st_mtime_ns
        while server.poll() is None:
            time.sleep(max(args.poll_seconds, 1.0))
            current_mtime = args.db.resolve().stat().st_mtime_ns
            if current_mtime != last_mtime:
                refreshed = build_snapshot(args.db)
                last_mtime = current_mtime
                if refreshed["meta"]["dataset_status"] == "ok":
                    output.write_text(
                        json.dumps(refreshed, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    print(
                        f"Snapshot refreshed: {refreshed['meta']['last_date']} "
                        f"({refreshed['meta']['publication_days']} days)"
                    )
                else:
                    print(
                        "Database changed but validation failed; keeping the last good snapshot.",
                        file=sys.stderr,
                    )
        return server.returncode or 0
    except KeyboardInterrupt:
        server.terminate()
        try:
            return server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            return server.wait()


if __name__ == "__main__":
    raise SystemExit(main())
