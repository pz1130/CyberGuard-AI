#!/usr/bin/env python3
"""Simple HTTP server for CyberGuard WebUI - serves the SPA at http://localhost:3000
Also proxies API calls to the FastAPI backend at localhost:8000.
"""
import http.server
import socketserver
import os
import urllib.request
import urllib.parse
import json

PORT = 3000
API_BASE = "http://localhost:8000"


class CyberGuardProxy(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            # Proxy to FastAPI (trim /api prefix → http://localhost:8000/api/v1/...)
            url = API_BASE + self.path  # full path: /api/v1/... → http://localhost:8000/api/v1/...
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host",)}
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            # Serve static files
            path = self.path.split("?")[0]
            if path == "/":
                path = "/index.html"
            file_path = os.path.join(os.path.dirname(__file__), path.lstrip("/"))

            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                mime_types = {
                    ".html": "text/html",
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                }
                self.send_response(200)
                self.send_header("Content-Type", mime_types.get(ext, "text/plain"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                # SPA fallback → index.html
                index = os.path.join(os.path.dirname(__file__), "index.html")
                if os.path.isfile(index):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(index, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path.startswith("/api/"):
            url = API_BASE + self.path[4:]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host",)}
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        if self.path.startswith("/api/"):
            url = API_BASE + self.path[4:]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host",)}
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            url = API_BASE + self.path[4:]
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host",)}
            try:
                req = urllib.request.Request(url, headers=headers, method="DELETE")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() not in ("transfer-encoding", "connection"):
                            self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[WebUI] {args[0]}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    print(f"Starting CyberGuard WebUI server at http://localhost:{PORT}")
    print(f"API proxy → {API_BASE}")
    print(f"Open: http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), CyberGuardProxy) as httpd:
        httpd.serve_forever()
