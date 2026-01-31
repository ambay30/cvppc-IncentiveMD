#!/usr/bin/env python3
"""
IncentiveMD Server with Census API Proxy
Run this script and open http://localhost:8090 in your browser

PRODUCTION NOTES:
- Uses ThreadingMixIn for concurrent request handling
- No external dependencies (Python stdlib only)
- Suitable for light-to-moderate traffic on Render.com free tier
- For high-traffic production, consider Gunicorn + Flask/FastAPI
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import re

PORT = int(os.environ.get('PORT', 8090))

# CORS configuration - supports local development and production
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'https://ambay30.github.io,http://localhost:8090,http://127.0.0.1:8090').split(',')

def get_cors_origin(request_origin):
    """Return appropriate CORS origin based on request"""
    if request_origin in ALLOWED_ORIGINS:
        return request_origin
    # Default to production origin
    return 'https://ambay30.github.io'


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    # Reduce server banner verbosity for security
    server_version = "IncentiveMD/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        """Override to add request logging with timestamps"""
        # In production, consider logging to file instead of stdout
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self):
        # Handle Census API proxy requests
        if self.path.startswith("/api/geocode-reverse"):
            self.handle_geocode_reverse()
        elif self.path.startswith("/api/geocode"):
            self.handle_geocode()
        else:
            # Serve static files
            super().do_GET()

    def handle_geocode(self):
        try:
            # Parse the address from query string
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            address = params.get("address", [""])[0]

            if not address:
                self.send_error(400, "Missing address parameter")
                return

            # Validate address length to prevent abuse
            if len(address) > 500:
                self.send_error(400, "Address too long (max 500 characters)")
                return

            # Try primary method: onelineaddress endpoint
            census_url = (
                f"https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
                f"?address={urllib.parse.quote(address)}"
                f"&benchmark=Public_AR_Current"
                f"&vintage=Census2020_Current"
                f"&format=json"
            )

            req = urllib.request.Request(
                census_url, headers={"User-Agent": "IncentiveMD/1.0"}
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
                response_json = json.loads(data)

                # Check if we got matches
                matches = response_json.get("result", {}).get("addressMatches", [])

                # If no matches and address has components, try component-based endpoint
                if not matches and "," in address:
                    # Try to parse into components
                    parts = [p.strip() for p in address.split(",")]

                    # Try to extract: street, city, state zip
                    if len(parts) >= 2:
                        street = parts[0]
                        city = parts[1] if len(parts) > 2 else ""
                        state_zip = parts[-1] if len(parts) > 1 else ""

                        # Parse state and zip from last component
                        state_zip_match = re.match(
                            r"([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?", state_zip.strip()
                        )
                        if state_zip_match:
                            state = state_zip_match.group(1)
                            zip_code = state_zip_match.group(2) or ""

                            # If we didn't extract city yet, try from middle component
                            if not city and len(parts) >= 3:
                                city = parts[-2].strip()
                            elif not city:
                                # City might be in the state_zip before state abbr
                                city_match = re.match(
                                    r"([A-Za-z\s]+)\s+[A-Z]{2}", state_zip
                                )
                                if city_match:
                                    city = city_match.group(1).strip()

                            # Try component-based endpoint
                            component_url = (
                                f"https://geocoding.geo.census.gov/geocoder/geographies/address"
                                f"?street={urllib.parse.quote(street)}"
                                f"&city={urllib.parse.quote(city)}"
                                f"&state={urllib.parse.quote(state)}"
                            )
                            if zip_code:
                                component_url += f"&zip={urllib.parse.quote(zip_code)}"
                            component_url += "&benchmark=Public_AR_Current&vintage=Census2020_Current&format=json"

                            req2 = urllib.request.Request(
                                component_url, headers={"User-Agent": "IncentiveMD/1.0"}
                            )

                            with urllib.request.urlopen(req2, timeout=15) as response2:
                                data = response2.read()
                                response_json = json.loads(data)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                origin = self.headers.get('Origin', '')
                self.send_header("Access-Control-Allow-Origin", get_cors_origin(origin))
                self.end_headers()
                self.wfile.write(json.dumps(response_json).encode('utf-8'))

        except urllib.error.URLError as e:
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass

    def handle_geocode_reverse(self):
        """Reverse geocode: coordinates → census tract"""
        try:
            # Parse the coordinates from query string
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            lat = params.get("lat", [""])[0]
            lng = params.get("lng", [""])[0]

            if not lat or not lng:
                self.send_error(400, "Missing lat or lng parameter")
                return

            # Validate coordinate ranges to prevent abuse
            try:
                lat_float = float(lat)
                lng_float = float(lng)
                if not (-90 <= lat_float <= 90):
                    self.send_error(400, "Latitude must be between -90 and 90")
                    return
                if not (-180 <= lng_float <= 180):
                    self.send_error(400, "Longitude must be between -180 and 180")
                    return
            except ValueError:
                self.send_error(400, "Invalid coordinate format")
                return

            # Census reverse geocoding endpoint
            census_url = (
                f"https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
                f"?x={urllib.parse.quote(lng)}"
                f"&y={urllib.parse.quote(lat)}"
                f"&benchmark=Public_AR_Current"
                f"&vintage=Census2020_Current"
                f"&format=json"
            )

            req = urllib.request.Request(
                census_url, headers={"User-Agent": "IncentiveMD/1.0"}
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
                response_json = json.loads(data)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            origin = self.headers.get('Origin', '')
            self.send_header("Access-Control-Allow-Origin", get_cors_origin(origin))
            self.end_headers()
            self.wfile.write(json.dumps(response_json).encode('utf-8'))

        except urllib.error.URLError as e:
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass

# Threaded server for concurrent request handling
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    Multi-threaded TCP server that handles each request in a separate thread.

    This prevents the server from blocking when waiting for Census API responses.
    Critical for batch processing where multiple geocoding requests are made.

    ThreadingMixIn is part of Python's standard library (no external dependencies).
    """
    # Allow reusing the address immediately after restart (prevents "Address already in use" errors)
    allow_reuse_address = True
    # Daemon threads automatically terminate when main thread exits
    daemon_threads = True


# Change to the directory containing this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"\n{'='*50}")
print("  IncentiveMD Server Running (Multi-threaded)")
print(f"{'='*50}")
print(f"\n  Open in browser: http://localhost:{PORT}")
print(f"  Mode: {'Production (Render)' if os.environ.get('PORT') else 'Development (Local)'}")
print("\n  Press Ctrl+C to stop the server")
print(f"{'='*50}\n")

with ThreadedTCPServer(("", PORT), ProxyHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
