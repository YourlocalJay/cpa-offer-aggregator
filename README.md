# CPA Offer Aggregator

This repository contains a command line tool for aggregating CPA offers from
multiple affiliate networks, filtering them based on geography, device
compatibility, payout thresholds and categories, and exporting the results
for use in other systems such as a cloaking engine or a tracking server.

## Features

- **Modular fetchers** for supported networks: MyLead (API), OGAds and
  CPAGrip (scraped via Playwright).
- **Unified filtering** with configurable GEO, device, payout and category
  criteria.
- **Tag‑based filtering** requiring offers to be Reddit‑safe or have
  no‑login requirements.
- **Exports** to both JSON and CSV formats.
- **Optional syncing**: copy the filtered offers into a sibling
  `aiqbrain-landing` repository for use by a Cloudflare Worker.

## Installation

Install Python dependencies and Playwright browsers:

```bash
pip install -r requirements.txt
playwright install
```

Copy `.env.example` to `.env` and populate it with your network API keys and
login credentials.

### MyLead token retrieval

The MyLead fetcher requires an access token. Provide your MyLead credentials via
the `MYLEAD_USERNAME` and `MYLEAD_PASSWORD` environment variables (for example
in your `.env` file). Tokens are fetched in-memory and injected into the
`MYLEAD_TOKEN` environment variable automatically when you run `main.py`.

To manually retrieve a token you can run:

```bash
python -c "from get_mylead_token import fetch_mylead_token; print(fetch_mylead_token())"
```

The token is not written to disk, avoiding stray credential files.

#### Troubleshooting

- **Missing credentials** – `fetch_mylead_token()` prints `❌ Missing MyLead
  credentials`. Ensure `MYLEAD_USERNAME` and `MYLEAD_PASSWORD` are set.
- **Invalid login** – a `401`/`403` response indicates incorrect credentials or
  an account issue. Verify your username/password and that the account is
  active.
- **Network errors** – connection timeouts or other `Login failed` messages can
  stem from network issues or API downtime. Retry once connectivity is restored.
- **Expired token** – if fetching offers starts returning `401` responses, run
  the aggregator again to refresh the token.

## Usage

Run the aggregator with optional filters:

```bash
python main.py --geo US --device Android --min-payout 1.50 --categories "Mobile Submits" "Giveaways" --sync
```

Options:

| Option         | Description                                                                                           | Default                |
|---------------|-------------------------------------------------------------------------------------------------------|------------------------|
| `--geo`        | ISO country code to target (e.g. `US`, `CA`, `UK`).                                                 | `US`                   |
| `--device`     | Device type to target (`Android`, `iOS`, `Desktop`, or `All`).                                      | `Android`              |
| `--min-payout` | Minimum payout threshold (float). Offers below this value are excluded.                             | `1.00`                 |
| `--categories` | Space‑separated list of preferred categories. Offers outside these categories will be excluded.       | `Mobile Submits Giveaways` |
| `--sync`       | If provided, automatically copy `cloudflare_offers.json` into the `aiqbrain-landing/public/data` folder | not set               |

Running without `--sync` will save the JSON and CSV files locally without
attempting to copy them to a landing repository. Use the `sync.py` script
for manual copying:

```bash
python sync.py
```

## Output Files

- `offers.json`: All offers fetched from the networks in raw form.
- `offers.csv`: CSV version of the raw offers for inspection in spreadsheet tools.
- `cloudflare_offers.json`: Filtered offers suitable for ingestion by a Cloudflare Worker.

## Extending

Additional networks can be supported by adding new fetcher modules under
`fetchers/` and importing them in `main.py`. The filtering logic can also
be extended or made configurable via additional command line options.

Tag inference rules are currently implemented in the fetchers; modify the
`_generate_tags` functions to incorporate new traffic rules or offer
attributes.
