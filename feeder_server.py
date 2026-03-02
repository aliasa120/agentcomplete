"""
Simple HTTP server that exposes the feeder pipeline as an HTTP endpoint.
Runs on port 8080 inside the backend container.
The frontend calls http://backend:8080/run to trigger the feeder.
"""
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FeederHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/run":
            try:
                result = subprocess.run(
                    ["python", "-m", "feeder.pipeline"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env={
                        **__import__("os").environ,
                        "PYTHONIOENCODING": "utf-8",
                        "PYTHONUTF8": "1",
                    },
                )
                success = result.returncode == 0
                response = {
                    "success": success,
                    "log": result.stdout,
                    "error": result.stderr if not success else "",
                }
                status = 200
            except subprocess.TimeoutExpired:
                response = {"success": False, "error": "Feeder pipeline timed out (5 min limit)"}
                status = 500
            except Exception as e:
                response = {"success": False, "error": str(e)}
                status = 500

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


def run():
    server = HTTPServer(("0.0.0.0", 8080), FeederHandler)
    print("✅ Feeder HTTP server running on port 8080", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
