# Cat Desk / Hyperliquid

A straight-facts Hyperliquid positioning dashboard. Dark green, mint, original pixel cats, and actual open books. Built in the same lightweight pattern as the sibling VVV dashboard: a static page, public JSON snapshots, and a scheduled Python collector.

## Run locally

Python 3.10+ is sufficient. No API key, package installation, wallet connection, or frontend build is required.

```powershell
python -m http.server 8080
```

Open **http://localhost:8080** from this directory. The included `data/snapshot.json` is real public-source data, with observation times. Open the page over HTTP rather than `file://`.

The dedicated **[xyz cohort desk](xyz.html)** is at **http://localhost:8080/xyz.html**, linked in the overview's navigation.

To update:

```powershell
python scripts/refresh.py --trader-limit 120 --top-traders 10
```

For a quick cohort/market update, including the xyz pair dashboard:

```powershell
python scripts/refresh.py --cohorts-only
```

The scan is intentionally paced below Hyperliquid's shared 1,200-weight/minute IP limit. New fill-history screening has an eight-minute budget by default, followed by position queries for the selected wallets. Known large xyz-position holders are checked first. The page reports successfully checked, deferred, incomplete, and failed wallet counts. For a broader scan use `--screen-budget 1800`. A two-hour screening checkpoint under `.cache/` lets repeated local runs resume with the same exact volume window and original PnL observation. Cohort/market data publishes before the longer screen starts. Failed sections retain their last good data with original timestamps and a visible refresh error.

## What's on the desk

- **Cohorts:** all-time perp-PnL bands from the Telegram report, plus account-size bands. Wallet counts, current long/short exposure, net positioning, and the largest allocation.
- **Asset allocation:** each cohort's ten largest markets, their long/short split, and the exact remaining notional labeled Other. Source top-ten coverage is visible.
- **Inside the book:** aggregate exposure ratio, positive open-PnL share, cohort membership change, and source-reported gross-exposure history.
- **Actual trades:** the cohort's largest 50 source-reported positions, with xyz/side filters, entry, mark, notional, unrealized PnL, liquidation, leverage, and wallet links.
- **Profitable xyz specialists:** verified >50% xyz share of executed **perp notional** in a complete 30-day fill window, ranked by positive official month **account PnL**. Wallet sheets query all currently registered perp DEXs.
- **xyz market tape:** mark, daily price change, daily executed volume, one-sided open interest, and hourly funding from the exchange.
- **Dedicated xyz cohort desk (`xyz.html`):** top-10/top-20 volume-ranked pair matrix against all eight PnL cohorts. Select a cell or pair for long/short dollars, net exposure, gross pair share, position counts, cohort comparisons, and public wallet samples with cohort/side filters. The matrix uses complete per-asset cohort feeds, not top-ten cohort allocations.
- **TradFi browser:** every active xyz market grouped as indices, commodities & energy, FX & rates, ETFs & funds, or single-name equities, with mark, 24h change, volume, open interest and funding. Tracked pairs jump straight into their eight-cohort breakdown.

## Navigation

Both pages share one menu. The `<nav id="site-nav">` markup is identical in `index.html` and `xyz.html`, behaviour lives in `nav.js`, and the test suite fails if the two ever diverge.

- **Overview** → `index.html`
- **Cohorts** → where the money sits, asset allocation, inside the book, largest open positions
- **XYZ desk** → cohort matrix, pair breakdown, reported trades, xyz specialists, market tape
- **TradFi** → all TradFi pairs, then each instrument group
- **Sources** → data sources, xyz coverage & method

Dropdowns open on hover for pointer devices and on click/tap for everything else; they close on Escape, on an outside click, or after a link is followed. Below 900px the whole menu collapses behind a **MENU** button. TradFi group links use `#tradfi-indices`, `#tradfi-commodities`, `#tradfi-fx`, `#tradfi-etfs` and `#tradfi-equities`, which the page uses to preselect that tab.

### xyz pair coverage and symbols

The collector follows the 20 busiest active xyz markets by **24h exchange-wide notional volume**, retaining NVDA, XYZ100, and SP500 if those reference markets fall outside the top 20. The page's “All tracked” option refers to this collected set. Pair order is market volume; it does not claim to measure each cohort's executed volume.

For the requested QQQ/SPY index view, the venue currently lists the actual markets **`xyz:XYZ100`** and **`xyz:SP500`**. These are distinct market symbols, not QQQ/SPY ETF listings. NVDA is `xyz:NVDA`.

For each pair, the collector fetches:

- `https://dw3ji7n7thadj.cloudfront.net/aggregator/assets/{coin}/coin-position-breakdown-by-cohort.json`
- `https://dw3ji7n7thadj.cloudfront.net/aggregator/assets/{coin}/positions.json`

The first source's `cohortMetrics` contains per-pair exposure across both size and PnL cohorts. Only PnL IDs 8–15 are used, avoiding overlap/double-counting. Short notional is gross minus long; net exposure is long minus short. Long share is long divided by gross. Missing cohorts remain unavailable; explicit zero gross exposure is flat. Each cohort record's actual source timestamp is retained.

The second source is a **public position sample**, separately labeled and deduplicated. Cohort membership uses its profile segment IDs. Visible sample trades are never summed as a substitute for aggregate cohort exposure. A sample's empty filter result is not evidence of a flat cohort.

The existing full refresh and `--cohorts-only` refresh both update `snapshot.xyz`. The scheduled workflow therefore updates both dashboards automatically when deployed. No trader-fill rescan is required for this new page.

## Sources & research

### 1. Existing daily Telegram report: HyperTracker / Coin Market Manager

Discovered in `../VVVDashboard/scripts/cohort_daily.py`:

- [HyperTracker](https://app.coinmarketman.com/hypertracker)
- [Public cohort definitions and aggregates](https://dw3ji7n7thadj.cloudfront.net/aggregator/segments.json)
- [Feed status](https://dw3ji7n7thadj.cloudfront.net/aggregator/status.json)
- `https://dw3ji7n7thadj.cloudfront.net/aggregator/segment_{id}.json`: allocations, largest positions, history, and open-book summary.

The eight PnL cohorts are IDs 8–15. The eight size cohorts are IDs 1–7 and 16. These are two overlapping classifications; totals use the PnL set only. HyperTracker's original cohort names and criteria are retained. Long share is recomputed as `long / (long + short)`; the source `perpBias` is equity-normalized and must not be mistaken for a percentage.

### 2. Additional primary source: official Hyperliquid leaderboard

- [Official leaderboard JSON](https://stats-data.hyperliquid.xyz/Mainnet/leaderboard)

The `month` window supplies account PnL, ROI, and a contextual reported volume. Rank is **account PnL**, not xyz-specific PnL or closed-trade PnL. The leaderboard's rolling window is observed independently of the exact 30-day fill window; both timestamps are retained. Its reported volume is not used as the denominator for xyz share.

Candidate discovery takes the top 120 profitable account-PnL wallets and adds profitable leaderboard wallets found in the source's largest xyz-position samples. Known large xyz holders are prioritized within the scan's time budget. This is a bounded screen, **not** an exhaustive or global xyz ranking. Counts of candidates, successful checks, deferred wallets, complete histories, incomplete histories, and failed checks are visible.

### 3. Additional primary source: Hyperliquid Info API

- [General Info API documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- [Perpetuals documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [API weight limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

Public read-only POSTs to `https://api.hyperliquid.xyz/info`:

| Type | Use |
| --- | --- |
| `userFillsByTime` | Executed notional and xyz share, paginated with inclusive timestamp-boundary deduplication |
| `perpDexs` | Discover all currently registered perp venues |
| `clearinghouseState`, per DEX | Current open positions, entry, liquidation, leverage, notional, and unrealized PnL |
| `metaAndAssetCtxs`, `dex: xyz` | xyz instruments, mark, 24h volume, open interest and funding |

`userFillsByTime` returns at most 2,000 fills per page and retains only the newest 10,000. Pagination reaching 10,000, a saturated timestamp boundary, or the page budget is **incomplete**. Such wallets cannot pass the verified-majority screen, even if the observed sample is 100% xyz. An API failure is never treated as an empty or flat account.

Executed perp volume is `abs(size) * execution_price` summed over all perp DEXs. Spot fills are excluded. `xyz:` prefixes identify XYZ's HIP-3 markets. XYZ closed-trade PnL is separately labeled **before fees/funding**; it does not include current unrealized PnL. All USD labels follow the sources' USD/stablecoin notional conventions; no independent collateral FX repricing is performed.

### 4. Venice Crypto RPC: checked at runtime

- [Authoritative live network list](https://api.venice.ai/api/v1/crypto/rpc/networks)
- [Venice Crypto RPC docs](https://docs.venice.ai/api-reference/endpoint/crypto/rpc)

At initial research, the live network list did not include Hyperliquid or HyperEVM. No Venice API key was available in this session. The collector rechecks the public network list and publishes that result. Hyperliquid trader positions/fills are HyperCore data, so even future HyperEVM JSON-RPC support would not replace the native Info API. No credentials are embedded in the site.

## Interpretation

- **Gross exposure** adds both long and short notionals. Do not compare it directly to one-sided exchange open interest or call it invested capital.
- Detail files and top-level cohort totals are independently observed. Allocation percentages reconcile against the detail file's own gross total.
- A position sample is not the complete cohort book. Filtering 50 largest positions to xyz does not discover every xyz position.
- Open-PnL profit share is not historical win rate. Leverage shown on a trade is its source-reported setting, not independently inferred whole-wallet leverage.
- Wallets/subaccounts are not people. Positions on other exchanges, spot holdings, open orders, or unqueried failed venues can change the overall economic view.
- The exposure-history plot has a visibly labeled cropped vertical axis. It plots only source-provided history.
- After six hours, each stale data section is explicitly flagged. Reload fetches the published JSON; it does not trigger a collector or pretend the page is streaming live.

## Deploy / scheduled updates

Create a GitHub repository for this folder and enable GitHub Pages from its default branch, root directory. The included workflow runs every four hours at minute 17 and supports a manual run. The workflow publishes refreshed JSON with the repository's normal `GITHUB_TOKEN` (Contents: write); no repository secrets are required. Allow write permissions for Actions in the repository settings. A partial refresh publishes successful sections, retains dated last-good sections, and marks the workflow failed.

This project has not been committed, pushed, or deployed by the local build.

## Checks

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
node --check app.js
node --check xyz.js
```

Tests cover executed-notional accounting, spot exclusion, cross-venue denominators, fill-boundary deduplication, retention caps, incomplete history, failed requests, signed positions, allocation reconciliation, per-pair net exposure, overlapping cohort exclusion, missing versus flat cohorts, duplicate rejection, and sample deduplication. Browser checks should also cover matrix/pair selection, top-10/top-20 views, trade filters, navigation between dashboards, stale/missing data, and mobile scrolling.

## Files

```text
index.html                 Dashboard structure
styles.css                 Responsive mint/dark desk styling
app.js                     Rendering, filters, charts, freshness, wallet sheets
xyz.html                   Dedicated xyz pair / PnL cohort dashboard
xyz.js                     Pair matrix, breakdowns, samples, coverage
xyz.css                    xyz matrix and pair-specific responsive styling
assets/cat.svg             Original pixel cat (no NFT artwork copied)
data/snapshot.json         Public, timestamped real-source data
scripts/refresh.py         Standard-library collector
scripts/test_refresh.py    Financial-accounting and coverage checks
.github/workflows/refresh.yml
```
