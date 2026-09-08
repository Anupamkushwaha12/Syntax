"""
Simple static file server for the FoodBridge frontend.
Serves index.html and api.js on http://localhost:5500
Run this alongside the backend (run.py).
"""
import http.server
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logs


class SilentServer(http.server.HTTPServer):
    def handle_error(self, request, client_address):
        pass  # suppress ConnectionAbortedError noise

print("Frontend running at: http://localhost:5500")
print("Open http://localhost:5500 in your browser")
SilentServer(("localhost", 5500), Handler).serve_forever()
