# Cat Desk / Hyperliquid

A straight-facts Hyperliquid and cross-platform positioning dashboard. Dark green, mint, an original detective cat, and actual source observations. Built in the same lightweight pattern as the sibling VVV dashboard: static pages, public JSON snapshots, and scheduled Python collectors.

## Run locally

Python 3.10+ is sufficient to serve the published snapshots. Viewing needs no API key, package installation, wallet connection, or frontend build. Refreshing eToro uses repository secrets in GitHub Actions.

```powershell
python -m http.server 8080
```

Open **http://localhost:8080** from this directory. The included `data/snapshot.json` is real public-source data, with observation times. Open the page over HTTP rather than `file://`.

The dedicated **[xyz cohort desk](xyz.html)** is at **http://localhost:8080/xyz.html**, linked in the overview's navigation. The published copy lives at **https://glitch46.github.io/hyperliquid-cat-desk/**.

The **[cross-platform desk](platforms.html)** is at **http://localhost:8080/platforms.html**, under **XYZ desk → Across platforms** on every page.

To update:

```powershell
python scripts/refresh.py --trader-limit 120 --top-traders 10
```

For a quick cohort/market update, including the xyz pair dashboard:

```powershell
python scripts/refresh.py --cohorts-only
```

The scan is intentionally paced below Hyperliquid's shared 1,200-weight/minute IP limit. New fill-history screening has an eight-minute budget by default (`--screen-budget`), followed by position queries for the selected wallets. Known large xyz-position holders are checked first. The page reports successfully checked, deferred, incomplete, and failed wallet counts. For a broader scan use `--screen-budget 1800`. A screening checkpoint under `.cache/` lets repeated runs resume the same volume window (reused for up to eight hours), so the scheduled workflow accumulates coverage across runs instead of restarting the pool every four hours. Cohort/market data publishes before the longer screen starts. Failed sections retain their last good data with original timestamps and a visible refresh error.

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

All three pages share one menu. The `<nav id="site-nav">` markup is identical in `index.html`, `xyz.html`, and `platforms.html`; behavior lives in `nav.js`.

- **Overview** → dashboard home, where the money sits, asset allocation, inside the book, largest open positions
- **XYZ desk** → cohort matrix, pair breakdown, open trades, **TradFi markets**, xyz specialists, **Across platforms**
- **Sources** → data sources, coverage & method

Cohorts is no longer a separate top-level item: its four section links now sit under **Overview**, keeping the bar at three dropdowns.

TradFi has no top-level menu of its own: it lives inside **XYZ desk**, because the TradFi instruments are xyz markets. The per-group submenus (`#tradfi-indices`, `#tradfi-commodities`, `#tradfi-fx`, `#tradfi-etfs`, `#tradfi-equities`) were dropped from the menu to keep it short, but those hashes still preselect the corresponding tab in the TradFi section.

Menus open on hover for pointer devices and on click/tap everywhere else; a click pins the menu open, and Escape, an outside click, or following a link closes it. A transparent 9px bridge covers the gap between the trigger and the panel so hover survives the trip down into the submenu — without it the menu closed the moment the pointer left the button. Below 900px the whole menu collapses behind a **MENU** button.

### xyz pair coverage and symbols

The collector follows the 20 busiest active xyz markets by **24h exchange-wide notional volume**, retaining NVDA, XYZ100, and SP500 if those reference markets fall outside the top 20. The page's “All tracked” option refers to this collected set. Pair order is market volume; it does not claim to measure each cohort's executed volume.

For the requested QQQ/SPY index view, the venue currently lists the actual markets **`xyz:XYZ100`** and **`xyz:SP500`**. These are distinct market symbols, not QQQ/SPY ETF listings. NVDA is `xyz:NVDA`.

For each pair, the collector fetches:

- `https://dw3ji7n7thadj.cloudfront.net/aggregator/assets/{coin}/coin-position-breakdown-by-cohort.json`
- `https://dw3ji7n7thadj.cloudfront.net/aggregator/assets/{coin}/positions.json`

The first source's `cohortMetrics` contains per-pair exposure across both size and PnL cohorts. Only PnL IDs 8–15 are used, avoiding overlap/double-counting. Short notional is gross minus long; net exposure is long minus short. Long share is long divided by gross. Missing cohorts remain unavailable; explicit zero gross exposure is flat. Each cohort record's actual source timestamp is retained.

The second source is a **public position sample**, separately labeled and deduplicated. Cohort membership uses its profile segment IDs. Visible sample trades are never summed as a substitute for aggregate cohort exposure. A sample's empty filter result is not evidence of a flat cohort.

The existing full refresh and `--cohorts-only` refresh both update `snapshot.xyz`. The cross-platform desk has an independent daily collector, so it needs no trader-fill rescan.

## Cross-platform desk

`platforms.html` compares **exactly twenty** pairs from the latest XYZ snapshot. A platform selector provides individual views; comparison checkboxes combine source columns without adding incompatible measurements. Ticker selection drives the pair evidence, sampled positions, eToro return cohorts, and daily records. Broader activity lists highlight validated overlaps and can jump directly to a pair. `xyz.html?pair=xyz:NVDA#pair-detail` supports links into the full XYZ book.

### Sources and measurement bases

| Platform | Data collected | Definition / coverage |
| --- | --- | --- |
| Hyperliquid | Existing XYZ market, cohort, and wallet samples | USD open notional, lifetime-dollar-PnL cohorts; broader XYZ list ranks rolling 24h executed notional. |
| eToro | Authenticated official **public-market and named public-investor** endpoints | Native buy/sell holdings fields, seven-day unique instrument viewers, public direct allocations and positions, MTD fractional investor gains. No private account endpoints. |
| Robinhood | Public Investor Index page's embedded `__NEXT_DATA__` | The published top-ten investment ranks, not per-stock dollar weights or executed volume. The index is conviction-weighted and excludes ETFs/options/crypto. |
| Schwab | Public embedded STAX chart and monthly report API | The report's labeled top-five net-buy/top-five net-sell table and monthly STAX score. Narrative mentions are not inferred as ticker flows. |
| IBKR | Access/coverage status and official documentation link | Not connected: no account or broker-wide public positions feed is available here. Market scanners are not treated as IBKR-only customer activity. |

Source references:

- eToro: [API portal](https://api-portal.etoro.com/), `https://public-api.etoro.com/api/v1/market-data/search`, `/api/v2/portfolios/rankings`, `/api/v1/user-info/people/{username}/portfolio/live`.
- Robinhood: [Investor Index and methodology](https://robinhood.com/us/en/investor-index/).
- Schwab: [STAX and methodology](https://www.schwab.com/investment-research/stax/view-schwab-trading-activity-index); the embedded page calls `https://stax-xapi.schwab.com/public/chart-data` and `/stax-data/{mmddyyyy}` with the public client headers from its own script.
- IBKR: [market scanner definitions](https://www.ibkrguides.com/traderworkstation/market-scanner-types.htm).

### eToro units and sample

The v2 ranking `gain` field is a **decimal fraction** (`0.10` = 10%); the portfolio `investmentPct` and position `netProfit` fields are **percentage points**. Public dollar balances are not derived. Four eToro-specific groups use **current-calendar-month** returns: ≥10%, 0 to <10%, −10 to <0%, and <−10%. These are not Hyperliquid Money Printer/Smart Money cohorts or rolling-30-day returns.

Discovery requests most-copied, highest-gain, lowest-gain, and most-trades ranking pages, then reads up to 60 public investor portfolios. It is a bounded sample, not all eToro customers. A username is deduplicated across discovery pages; direct position IDs are deduplicated inside each account. Nested copy portfolios are not expanded because the API does not specify that their percentages use the direct-account allocation denominator.

Sample allocation split = sum of direct long portfolio-percentage points ÷ sum of direct long + short points. It is an **equal-account allocation measure**, not dollar-weighted exposure. Mean allocation includes successfully sampled portfolios with no direct position. Empty samples remain unknown. Broker-reported buy/sell holdings percentages are shown separately; their documentation does not establish a dollar-notional denominator.

The eToro activity list is **seven-day unique viewers**, explicitly not executed trades or volume. Robinhood and Schwab lists retain monthly periods and their own units. No combined volume total, invented blended buy percentage, or cross-broker unique-person count is published.

### Matching

Equity/fund identities require an exact platform symbol. SPCX also requires the SpaceX name to prevent ticker reuse from matching an unrelated fund. Index/commodity contracts such as NSDQ100 versus XYZ100 are explicit **reference instruments**, excluded from direct-overlap coverage counts. QQQ/SPY are not silently equated with XYZ100/SP500. Unknown synthetics stay unmapped rather than matching a similar-looking ticker.

### Daily collection

The `Refresh cross-platform data` workflow runs at **22:40 UTC Monday–Friday**, after the regular US equity close in both standard and daylight-saving time. It reads `ETORO_API_KEY` and `ETORO_USER_KEY` from repository Actions secrets, uses read-only GET endpoints, and publishes only normalized public analytics. Secrets and private account data are not written to snapshots or the browser. `probe_only=true` checks public endpoint access without publishing.

```powershell
python scripts/platforms.py --public-only
```

The public-only local command refreshes Hyperliquid, Robinhood, and Schwab and retains any previous authenticated eToro observation. Full authenticated collection runs in Actions with `python -u scripts/platforms.py --sample-limit 60`.

Files: `data/platforms.json` and `data/platforms_history.json`. History keeps one replaceable observation per UTC collection day for 90 days, with each source's actual observation time preserved. Monthly reports do not become daily facts simply because the collector ran again. Failed sources keep last-good data and dates; unavailable values never become zero. Initial history builds from the first real collection day—there is no simulated backfill.

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

Published from this repository with GitHub Pages (default branch, root):

- Dashboard: **https://glitch46.github.io/hyperliquid-cat-desk/**
- xyz cohort desk: **https://glitch46.github.io/hyperliquid-cat-desk/xyz.html**
- Cross-platform desk: **https://glitch46.github.io/hyperliquid-cat-desk/platforms.html**
- Repo: **https://github.com/glitch46/hyperliquid-cat-desk**

The Hyperliquid workflow runs every four hours at minute 17; the broker workflow runs after the US close on weekdays. Both support manual runs and share a concurrency group so refresh commits cannot race. Hyperliquid uses public endpoints; the broker workflow uses the two eToro secrets. The normal `GITHUB_TOKEN` publishes public JSON with Contents: write. A partial refresh retains dated last-good sections and surfaces failures.

## Checks

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
node --check app.js
node --check nav.js
node --check xyz.js
node --check platforms.js
```

Tests cover executed-notional accounting, spot exclusion, cross-venue denominators, fill-boundary deduplication, retention caps, incomplete history, failed requests, signed positions, allocation reconciliation, per-pair net exposure, overlapping cohort exclusion, missing versus flat cohorts, duplicate rejection, and sample deduplication. Browser checks should also cover matrix/pair selection, top-10/top-20 views, trade filters, navigation between dashboards, stale/missing data, and mobile scrolling.

## Files

```text
index.html                 Dashboard structure
styles.css                 Responsive mint/dark desk styling
app.js                     Rendering, filters, charts, freshness, wallet sheets
nav.js                     Shared dropdown navigation (all three pages)
xyz.html                   Dedicated xyz pair / PnL cohort dashboard
xyz.js                     Pair matrix, breakdowns, samples, coverage
xyz.css                    xyz matrix and pair-specific responsive styling
platforms.html             Individual and combined platform views
platforms.js               Source comparison, portfolios, activity, daily records
platforms.css              Cross-platform desk styling
assets/cat-detective.svg   Original detective-cat mascot (hand-authored SVG,
                           drawn in a similar style to the reference, not a copy)
data/snapshot.json         Public, timestamped real-source data
scripts/refresh.py         Standard-library collector
scripts/test_refresh.py    Financial-accounting and coverage checks
scripts/etoro.py           Read-only public-market/public-investor API client
scripts/platforms.py       End-of-day broker collector and 20-pair mapping
scripts/test_platforms.py  Identity, source units, and sample-accounting checks
.github/workflows/refresh.yml
.github/workflows/platforms.yml
```
