# IncentiveMD v1.0

**30C Tax Credit Eligibility Checker**

A cloud-hosted tool for checking IRS 30C Alternative Fuel Vehicle Refueling Property Credit eligibility based on census tract location.

## Live Demo

**Production URL**: `https://ambay30.github.io/cvppc-IncentiveMD`

## Features

- **Address Geocoding**: Uses Census Bureau Geocoding API for accurate location data
- **IRS Appendix B Validation**: Checks 55,474 eligible census tracts from IRS Notice 2024-20
- **Interactive Map**: Leaflet.js + OpenStreetMap visualization with color-coded markers
- **Batch Processing**: Upload CSV files with up to 1,000 addresses
- **Manual Override**: Add custom census tracts for special cases
- **CSV Export**: Export results with coordinates and eligibility status

## Eligibility Types

- **NMTC (New Markets Tax Credit)**: Low-income communities (valid through 2029-12-31)
- **Non-Urban**: Rural census tracts (valid through 2032-12-31)
- **Both**: Tracts eligible under both criteria

## Architecture

### Frontend (GitHub Pages)
- **File**: `index.html` (3.27 MB with inline eligibility data)
- **Hosting**: GitHub Pages at `https://ambay30.github.io/cvppc-IncentiveMD`
- **Technology**: Vanilla JavaScript, Leaflet.js, PapaParse

### Backend (Render.com)
- **File**: `serve.py` (Python CORS proxy)
- **Hosting**: Render.com at `https://cvppc-incentivemd.onrender.com`
- **Purpose**: Proxy Census Bureau API requests to add CORS headers
- **Endpoints**:
  - `/api/geocode?address=...` - Forward geocoding (address → coordinates)
  - `/api/geocode-reverse?lat=...&lng=...` - Reverse geocoding (coordinates → census tract)

## Local Development

### Prerequisites
- Python 3.11+ (no external dependencies)
- Modern web browser

### Setup
```bash
# Clone repository
git clone https://github.com/ambay30/cvppc-IncentiveMD.git
cd cvppc-IncentiveMD

# Start local server
python3 serve.py

# Open browser
open http://localhost:8090
```

The application automatically detects local development and uses `http://localhost:8090` for API calls instead of the production Render URL.

## Usage

### Single Address Lookup
1. Enter address in search box (e.g., "120 Rowan Street, Fayetteville, NC 28301")
2. Click "Check Eligibility"
3. View result with map marker and eligibility status

### Batch Processing
1. Prepare CSV file with "Address" column header
2. Click "Upload CSV" and select file
3. View progress bar as addresses are processed
4. Review results in table with color-coded status
5. Export results to CSV with coordinates

### Example CSV Format
```csv
Address
120 Rowan Street, Fayetteville, NC 28301
1600 Pennsylvania Avenue NW, Washington, DC 20500
350 Fifth Avenue, New York, NY 10118
```

### Manual Override
1. Enter census tract GEOID (11-digit format: SSCCCTTTTTT)
2. Select eligibility type (NMTC, Non-Urban, Both)
3. Click "Add Override"
4. Override persists in browser localStorage

## Geocoding Strategy

The tool uses a 6-level fallback strategy for maximum address matching:

1. **Full Address**: `123 Main Street, City, ST 12345`
2. **DC Avenue Expansion**: `Pennsylvania Avenue → Pennsylvania Avenue NW/NE/SE/SW`
3. **Route Normalization**: `Route 1 → Highway 1, US 1, State Route 1`
4. **Component-Based**: Parse into street, city, state, zip
5. **City-Only Fallback**: Drop street address, use city centroid
6. **Manual Entry**: User can paste coordinates or census tract

## Data Sources

- **IRS Appendix B**: [IRS Notice 2024-20](https://www.irs.gov/pub/irs-drop/n-24-20.pdf)
- **Census Bureau API**: [Geocoding Services](https://geocoding.geo.census.gov/)
- **OpenStreetMap**: [Leaflet.js](https://leafletjs.com/) for mapping

## Deployment

### GitHub Pages (Frontend)
1. Push changes to `main` branch
2. GitHub Pages auto-deploys in ~1 minute
3. Access at `https://ambay30.github.io/cvppc-IncentiveMD`

### Render.com (Backend)
1. Connect GitHub repository to Render
2. Configure web service:
   - **Build Command**: (leave blank)
   - **Start Command**: `python serve.py`
   - **Environment**: Python 3
3. Render auto-deploys on push to `main`
4. Backend available at `https://cvppc-incentivemd.onrender.com`

## Free Hosting Limits

- **GitHub Pages**: Unlimited bandwidth (soft limit: 100 GB/month)
- **Render.com Free Tier**: 750 hours/month (~31 days)
- **Census Bureau API**: No published rate limits (respectful usage recommended)

## Technical Details

### File Sizes
- `index.html`: 3.27 MB (includes 55,474 inline census tracts)
- `serve.py`: 9.4 KB
- Total repository: ~3.3 MB

### Browser Compatibility
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Performance
- Single address: ~1-2 seconds (geocoding)
- Batch processing: ~1 address/second (Census API rate limiting)
- Map rendering: Instant (Leaflet.js)

## Security

- **CSV Sanitization**: Prevents formula injection attacks (=, +, @, -)
- **Input Validation**: Address length limits, GEOID format validation
- **CORS Restrictions**: Backend only accepts requests from GitHub Pages domain
- **No API Keys**: Census Bureau API is public (no authentication required)

## Support

- **Issues**: Report bugs at `https://github.com/ambay30/cvppc-IncentiveMD/issues`
- **Questions**: Contact repository owner

## License

Internal use - Commercial Vehicle Parking & Power Collective (CVPPC)

## Version History

- **v1.0** (2026-01-30): Public release
  - Cloud-hosted deployment (GitHub Pages + Render)
  - 55,474 inline eligible census tracts
  - Enhanced Excel/CSV validation and error handling
  - Census Bureau API geocoding with 6-level fallback
  - Interactive map visualization
  - Batch processing (up to 5,000 addresses)
  - Manual census tract override feature
  - CSV export with coordinates

## Credits

Built with:
- [Leaflet.js](https://leafletjs.com/) - Map visualization
- [PapaParse](https://www.papaparse.com/) - CSV parsing
- [Census Bureau Geocoding API](https://geocoding.geo.census.gov/)
- [OpenStreetMap](https://www.openstreetmap.org/) - Map tiles
