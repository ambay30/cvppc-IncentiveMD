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
import time
from collections import defaultdict
from threading import Lock

PORT = int(os.environ.get('PORT', 8090))

# Rate limiting configuration
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30  # requests per window per IP
rate_limit_data = defaultdict(list)
rate_limit_lock = Lock()

# CORS configuration - supports local development and production
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'https://ambay30.github.io,http://localhost:8090,http://127.0.0.1:8090').split(',')

def get_cors_origin(request_origin):
    """Return appropriate CORS origin based on request"""
    if request_origin in ALLOWED_ORIGINS:
        return request_origin
    # Default to production origin
    return 'https://ambay30.github.io'

def sanitize_input(text, max_length=500):
    """Sanitize input to prevent injection attacks"""
    if not text:
        return ""
    # Remove null bytes and control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\t\n\r')
    # Truncate to max length
    text = text[:max_length]
    return text.strip()

def check_rate_limit(ip_address):
    """Check if IP has exceeded rate limit. Returns (allowed, retry_after)"""
    current_time = time.time()

    with rate_limit_lock:
        # Clean old entries
        rate_limit_data[ip_address] = [
            timestamp for timestamp in rate_limit_data[ip_address]
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]

        # Check limit
        if len(rate_limit_data[ip_address]) >= RATE_LIMIT_MAX_REQUESTS:
            oldest = min(rate_limit_data[ip_address])
            retry_after = int(RATE_LIMIT_WINDOW - (current_time - oldest)) + 1
            return False, retry_after

        # Add current request
        rate_limit_data[ip_address].append(current_time)
        return True, 0


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    # Reduce server banner verbosity for security
    server_version = "IncentiveMD/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        """Override to add request logging with timestamps"""
        # Reduce logging verbosity in production
        if os.environ.get('PORT'):  # Production (Render)
            # Only log errors and API calls, not static file requests
            if 'api' in self.path or 'health' in self.path or '40' in format or '50' in format:
                print(f"[{self.log_date_time_string()}] {format % args}")
        else:  # Local development
            print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self):
        # Check request size limit (prevent large query strings)
        if len(self.path) > 2000:
            self.send_error(414, "Request-URI Too Long")
            return

        # Get client IP for rate limiting
        client_ip = self.client_address[0]

        # Health check endpoint for monitoring
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","version":"1.0"}')
            return

        # Handle Census API proxy requests
        elif self.path.startswith("/api/geocode-reverse"):
            # Apply rate limiting
            allowed, retry_after = check_rate_limit(client_ip)
            if not allowed:
                self.send_response(429)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Retry-After", str(retry_after))
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Rate limit exceeded. Please try again later.",
                    "retry_after": retry_after
                }).encode('utf-8'))
                return
            self.handle_geocode_reverse()

        elif self.path.startswith("/api/geocode"):
            # Apply rate limiting
            allowed, retry_after = check_rate_limit(client_ip)
            if not allowed:
                self.send_response(429)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Retry-After", str(retry_after))
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Rate limit exceeded. Please try again later.",
                    "retry_after": retry_after
                }).encode('utf-8'))
                return
            self.handle_geocode()

        else:
            # Disable static file serving in production (security)
            if os.environ.get('PORT'):  # Production
                self.send_error(404, "Not Found")
            else:  # Local development
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

            # Sanitize and validate input
            address = sanitize_input(address, max_length=500)
            if not address:
                self.send_error(400, "Invalid address parameter")
                return

            # Additional validation
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
                        # Normalize to uppercase for case-insensitive matching
                        state_zip_match = re.match(
                            r"([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?", state_zip.strip().upper()
                        )
                        if state_zip_match:
                            state = state_zip_match.group(1)
                            zip_code = state_zip_match.group(2) or ""

                            # If we didn't extract city yet, try from middle component
                            if not city and len(parts) >= 3:
                                city = parts[-2].strip()
                            elif not city:
                                # City might be in the state_zip before state abbr
                                # Normalize to uppercase for case-insensitive matching
                                city_match = re.match(
                                    r"([A-Za-z\s]+)\s+[A-Z]{2}", state_zip.upper()
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

        except urllib.error.HTTPError as e:
            # HTTP error from upstream - pass through status code
            try:
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Geocoding service error" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg, "code": e.code}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except urllib.error.URLError as e:
            # Network error (timeout, connection refused, DNS failure, etc.)
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Geocoding service unavailable" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Internal server error" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass

    def handle_geocode_reverse(self):
        """Reverse geocode: coordinates → census tract"""
        try:
            # Parse the coordinates from query string
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            lat = sanitize_input(params.get("lat", [""])[0], max_length=20)
            lng = sanitize_input(params.get("lng", [""])[0], max_length=20)

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

        except urllib.error.HTTPError as e:
            # HTTP error from upstream - pass through status code
            try:
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Geocoding service error" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg, "code": e.code}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except urllib.error.URLError as e:
            # Network error (timeout, connection refused, DNS failure, etc.)
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Geocoding service unavailable" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, nothing to send
                pass
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                # Sanitize error message - don't leak internal details
                error_msg = "Internal server error" if os.environ.get('PORT') else str(e)
                self.wfile.write(json.dumps({"error": error_msg}).encode('utf-8'))
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
