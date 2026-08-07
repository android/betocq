# BeToCQ Test Explorer

The **BeToCQ Test Explorer** is a lightweight, zero-dependency local web
application designed to parse, visualize, and triage Mobly test execution
results across BeToCQ projects, including Osmosis connection testing
(Wi-Fi STA, Wi-Fi Aware, BLE, USB NCM).

## Goal & Purpose

When running Mobly tests locally or at partner OEM test stations, raw output
directories contain multi-document `test_summary.yaml` files, hundreds of
repeated test iterations, and deeply nested device logs.

BeToCQ Test Explorer provides an instant local web dashboard to:

1.  **Aggregate Repeats**: Group repeated test iterations (`test_case_0` ...
    `test_case_19`) into base test cards with green (`✓`) and red (`!`)
    iteration chips.
2.  **KPI Metrics & Progress**: Display visual pass-rate progress bars and
    high-level KPIs (Total, Passed, Failed, Skipped).
3.  **Hierarchical Breakdown**: Automatically format test suite names in clean
    CamelCase / TitleCase (e.g. `OsmosisSuwAwareTest`) with click-to-expand log
    drawers for failure stacktraces.
4.  **Sponge/BTX-Style Artifacts Tree**: Render a hierarchical, collapsible
    directory tree (`📁`) with clickable individual file download links and
    in-browser modal previews for test logs and YAML artifacts.
5.  **Universal & Hermetic**: Run natively across macOS and Linux with zero
    external web framework dependencies (`pip`, `flask`, `npm`, etc.).

## Architecture

-   **`server.py`**: A pure Python 3 standard library HTTP server
    (`http.server`) exposing REST endpoints for metrics (`/api/results`), zip
    uploads (`/api/upload`), in-browser text previews (`/api/artifact`), and
    direct file downloads (`/api/download`).
-   **`mobly_parser.py`**: Mobly YAML stream parser, repeat iteration
    aggregator, and recursive artifact indexer.
-   **`templates/index.html`**: Material 3 / Tailwind single-page application
    dashboard.
-   **`BUILD`**: Built with `launcher =
    "//devtools/python/launcher:no_launcher"` and `paropts =
    ["--interpreter=/usr/bin/env python3"]` to create a fast, launcher-free
    universal zipapp (`test_explorer.par`).

## Usage

### 1. Launch with Results Directory or Zip File

```bash
# Pass a zip file directly (positional argument)
./test_explorer.par /path/to/mobly_results.zip

# Pass a zip file via flag
./test_explorer.par --results_dir /path/to/mobly_results.zip

# Pass an extracted results directory
./test_explorer.par /path/to/mobly_results/
```

### 2. Launch in Interactive Upload Mode

```bash
./test_explorer.par
```

*(or `./osmosis.sh explore`)*

The server will automatically select an available port (or run on a port
specified via `--port <port>`), open your default browser, and display the
dashboard. Drag and drop any Mobly `.zip` test result archive to view the
dashboard.
