"""
Feeder HTTP server + optional cron auto-trigger.

- Runs on port 8080 inside the backend container.
- The frontend calls POST http://backend:8080/run to trigger the feeder manually.
- Auto-scheduler: reads `auto_run_interval_hours` from the Supabase `feeder_settings`
  table at startup and re-checks every hour. Set the value in Supabase to enable.
  Set to 0 (or leave unset) to disable.

  Example Supabase row to enable every 2 hours:
    INSERT INTO feeder_settings (key, value) VALUES ('auto_run_interval_hours', '2');
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
load_dotenv()


# ---------------------------------------------------------------------------
# Internal helper: run the feeder pipeline as a subprocess
# ---------------------------------------------------------------------------
def _run_pipeline() -> dict:
    try:
        result = subprocess.run(
            ["python", "-m", "feeder.pipeline"],
            capture_output=True,
            text=True,
            timeout=300,
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
        success = result.returncode == 0
        return {
            "success": success,
            "log": result.stdout,
            "error": result.stderr if not success else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Feeder pipeline timed out (5 min limit)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Cron auto-scheduler (runs in a background thread)
# ---------------------------------------------------------------------------
def _load_interval_hours() -> int:
    """Read feeder auto-trigger settings from Supabase feeder_settings. Returns 0 if disabled."""
    try:
        from feeder.db import supabase_client
        res = supabase_client.table("feeder_settings").select("key,value").in_(
            "key", ["feeder_auto_trigger_enabled", "feeder_auto_trigger_interval_hours"]
        ).execute()
        smap = {row["key"]: row["value"] for row in (res.data or [])}
        enabled = smap.get("feeder_auto_trigger_enabled", "false").lower() == "true"
        if not enabled:
            return 0
        return int(smap.get("feeder_auto_trigger_interval_hours", "2"))
    except Exception as e:
        print(f"[AutoScheduler] Could not load interval from Supabase: {e}", flush=True)
    return 0


def _scheduler_loop():
    """Background thread: sleeps until next scheduled run, then fires the pipeline."""
    print("[AutoScheduler] Cron thread started. Checking Supabase for auto_run_interval_hours...", flush=True)
    last_run: float = 0.0

    while True:
        interval_hours = _load_interval_hours()

        if interval_hours <= 0:
            # Scheduler disabled — sleep 60 s then re-check in case it's enabled later
            time.sleep(60)
            continue

        interval_secs = interval_hours * 3600
        now = time.time()
        secs_since_last = now - last_run

        if secs_since_last >= interval_secs:
            print(f"[AutoScheduler] ⏰ Auto-triggering feeder pipeline (interval={interval_hours}h)...", flush=True)
            result = _run_pipeline()
            last_run = time.time()
            if result["success"]:
                print("[AutoScheduler] ✅ Auto-run completed successfully.", flush=True)
            else:
                print(f"[AutoScheduler] ❌ Auto-run failed: {result['error'][:200]}", flush=True)
        else:
            wait_secs = interval_secs - secs_since_last
            print(f"[AutoScheduler] Next auto-run in {wait_secs/3600:.1f}h (interval={interval_hours}h).", flush=True)
            time.sleep(min(wait_secs, 60))  # Sleep up to 60s at a time to allow interval changes to take effect
            continue

        # After a run, wait the full interval before checking again
        time.sleep(60)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class FeederHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/run":
            response = _run_pipeline()
            status = 200 if response["success"] else 500
            body = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress noisy access logs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run():
    # Start background cron scheduler thread
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="feeder-cron")
    t.start()

    server = HTTPServer(("0.0.0.0", 8080), FeederHandler)
    print("✅ Feeder HTTP server running on port 8080", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
