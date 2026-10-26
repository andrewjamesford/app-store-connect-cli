# App Store Connect read-only CLI

Reusable local CLI for downloading App Store Connect apps, Sales and Trends reports, Finance reports, and Analytics Reports. It is deliberately read-only and separate from the FastTempo and Google reporting projects.

## What it provides

- `asc apps` to list apps visible to the API key
- `asc sales` to download Sales and Trends reports for iOS, iPadOS, and other Apple platforms
- `asc finance` to download monthly finance reports
- `asc analytics-requests` to list existing analytics report requests for an app
- `asc analytics-reports` to list generated analytics reports
- `asc analytics-instances` to list time-bounded report instances
- `asc analytics-download` to download and parse all segments for an instance
- table, JSON, CSV, and TSV output

## Credentials

App Store Connect uses JWT authentication. Create or request App Store Connect API access, then create a Team API key with the least role needed. Sales and Finance reports require a Team key; an Individual key cannot access those endpoints.

You need:

- Issuer ID
- Key ID
- The downloaded private `.p8` key
- Vendor number for Sales and Finance reports

The CLI reads these from `ASC_ISSUER_ID`, `ASC_KEY_ID`, `ASC_PRIVATE_KEY`, and `ASC_VENDOR_NUMBER`, or from the corresponding global flags. Store the key outside the repo, for example:

```bash
mkdir -p ~/.config/app-store-connect-cli
chmod 700 ~/.config/app-store-connect-cli
cp ~/Downloads/AuthKey_ABC123.p8 ~/.config/app-store-connect-cli/
chmod 600 ~/.config/app-store-connect-cli/AuthKey_ABC123.p8
export ASC_ISSUER_ID="your-issuer-id"
export ASC_KEY_ID="ABC123"
export ASC_PRIVATE_KEY="$HOME/.config/app-store-connect-cli/AuthKey_ABC123.p8"
export ASC_VENDOR_NUMBER="your-vendor-number"
```

## Setup

```bash
cd /Users/andrewford/Developer/tools/app-store-connect-cli
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Examples

```bash
# List apps first to find App Store Connect app IDs
.venv/bin/asc apps

# Download the latest daily Sales and Trends summary as CSV
.venv/bin/asc --format csv sales > sales.csv

# Download a monthly finance report for a region
.venv/bin/asc --format csv finance \
  --region-code WW \
  --report-date 2026-07 > finance.csv

# Explore existing App Analytics report data for an app
.venv/bin/asc --format json analytics-requests --app-id 123456789
.venv/bin/asc --format json analytics-reports --request-id REQUEST_ID
.venv/bin/asc --format json analytics-instances --report-id REPORT_ID
.venv/bin/asc --format csv analytics-download --instance-id INSTANCE_ID > app-analytics.csv
```

Sales report dates use Apple's reporting rules. Daily reports do not require `--report-date`; weekly, monthly, and yearly reports do. Finance dates use Apple's fiscal calendar in `YYYY-MM` format. Apple may apply privacy thresholds and noise to Analytics Reports, so missing low-volume rows do not necessarily mean zero activity.

## Security choices

- JWTs are generated in memory for each request and are never written to disk.
- Private `.p8` keys are ignored by git and checked for restrictive file permissions.
- No App Store Connect write endpoints are exposed.
- Presigned Analytics segment URLs are downloaded immediately and not persisted by the CLI.

## Development

```bash
python3 -m pip install -e '.[test]'
python3 -m pytest
```

