#!/usr/bin/env python3
"""
IncentiveMD Server with Census API Proxy
Run this script and open http://localhost:8090 in your browser
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import re

PORT = int(os.environ.get('PORT', 8090))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
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

            with urllib.request.urlopen(req, timeout=30) as response:
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

                            with urllib.request.urlopen(req2, timeout=30) as response2:
                                data = response2.read()
                                response_json = json.loads(data)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "https://ambay30.github.io")
                self.end_headers()
                self.wfile.write(json.dumps(response_json).encode())

        except urllib.error.URLError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

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
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "https://ambay30.github.io")
            self.end_headers()
            self.wfile.write(json.dumps(response_json).encode())

        except urllib.error.URLError as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

# Change to the directory containing this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print(f"\n{'='*50}")
print("  IncentiveMD Server Running")
print(f"{'='*50}")
print(f"\n  Open in browser: http://localhost:{PORT}")
print("\n  Press Ctrl+C to stop the server")
print(f"{'='*50}\n")

with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
