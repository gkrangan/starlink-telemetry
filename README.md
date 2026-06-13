# starlink-telemetry

A Python library and CLI for pulling real-time telemetry, stats, and control from your **Starlink dish** via its local gRPC API. Works with all current hardware including the **Starlink Mini**.

---

## How it works

Every Starlink dish exposes a private gRPC service at `192.168.100.1:9200` on your local network. This tool talks directly to that endpoint — no Starlink account, no cloud, no internet required — using the same protobuf API the official Starlink app uses.

It uses **gRPC server reflection** via [yagrc](https://github.com/sparky8512/yagrc): the dish advertises its own API schema at connect time, so there are no proto files to compile or maintain. The schema stays in sync with your dish's firmware automatically.

---

## Requirements

- Python 3.9+
- Your machine connected to the Starlink network (dish reachable at `192.168.100.1`)

---

## Installation

```bash
git clone https://github.com/gkrangan/starlink-telemetry.git
cd starlink-telemetry

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

> **Note for macOS (Homebrew Python):** The `source .venv/bin/activate` step sets `PYTHONPATH` automatically — this is required due to a known Python 3.14 issue with editable installs in virtualenvs.

---

## Usage

All commands are available via the `starlink` CLI after activating the venv.

```bash
cd starlink-telemetry
source .venv/bin/activate
starlink --help
```

### Global options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `192.168.100.1` | Dish IP address |
| `--port` | `9200` | gRPC port |
| `--timeout` | `10.0` | Request timeout (seconds) |
| `--json` | off | Output raw JSON instead of formatted tables |

---

### `status` — current dish snapshot

```bash
starlink status
starlink --json status
```

Displays signal quality, throughput, latency, ping drop rate, pointing angles, GPS, obstruction percentage, active alerts, and device info.

**Example output:**
```
╭─────────────────────── Starlink Dish Status ───────────────────────╮
│ ╭──────────────────── Signal & Throughput ───────────────────────╮ │
│ │ Uptime           1h 52m 39s                                    │ │
│ │ Latency          22.2 ms                                       │ │
│ │ Ping drop        0.00%                                         │ │
│ │ SNR above noise  yes                                           │ │
│ │ Downlink         655.48 Kbps                                   │ │
│ │ Uplink           65.00 Kbps                                    │ │
│ │ Ethernet         1000 Mbps                                     │ │
│ │ Obstructed       no                                            │ │
│ │ Obstruction %    5.4%                                          │ │
│ ╰────────────────────────────────────────────────────────────────╯ │
│ ╭─────────────────── Pointing & State ───────────────────────────╮ │
│ │ Azimuth    5.3°                                                │ │
│ │ Elevation  68.7°                                               │ │
│ │ GPS valid  yes                                                 │ │
│ │ GPS sats   18                                                  │ │
│ │ Slots in   connected                                           │ │
│ │ Ready      all                                                 │ │
│ │ Stow req   no                                                  │ │
│ ╰────────────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────── Device ────────────────────────────────╮ │
│ │ ID        ut41780985-c611791c-59a90bde                         │ │
│ │ Hardware  mini1_panda_prod1                                    │ │
│ │ Software  2026.06.02.mr80873                                   │ │
│ │ Country   US                                                   │ │
│ ╰────────────────────────────────────────────────────────────────╯ │
╰───────────────────────────── alerts: none ─────────────────────────╯
```

---

### `watch` — live dashboard

```bash
starlink watch
starlink watch --interval 2
```

Auto-refreshing status panel. Press `Ctrl-C` to stop.

| Option | Default | Description |
|--------|---------|-------------|
| `--interval` | `1.0` | Refresh interval in seconds |

---

### `history` — historical stats

```bash
starlink history              # averaged summary (~12-hour window)
starlink history --raw        # full per-second sample arrays
starlink --json history       # JSON output for piping
```

The dish maintains a ring buffer of ~45,000 one-second samples (roughly 12 hours). The summary view shows averaged metrics; `--raw` dumps every array.

**Summary metrics:**
- Total samples in window
- Average ping drop rate (all + scheduled slots only)
- Average latency (ms)
- Average downlink / uplink throughput
- Fraction of time obstructed or without satellites

---

### `obstruction-map` — sky view

```bash
starlink obstruction-map
```

Renders the dish's sky obstruction bitmap as an ASCII grid. Filled blocks (`█`) represent clear sky; light blocks (`░`) are partially obstructed; spaces are blocked/no-data.

---

### `config` — view dish configuration

```bash
starlink config
starlink --json config
```

Shows power save schedule, snow melt mode, level-dish mode, and location request mode.

---

### `set-config` — update configuration

```bash
# Enable power save 02:00–10:00 UTC daily
starlink set-config --power-save --power-save-start 120 --power-save-duration 480

# Disable power save
starlink set-config --no-power-save

# Snow melt mode: 0=off, 1=on, 2=auto
starlink set-config --snow-melt-mode 2
```

| Option | Description |
|--------|-------------|
| `--power-save / --no-power-save` | Toggle power save mode |
| `--power-save-start MINUTES` | Start time (minutes from midnight UTC) |
| `--power-save-duration MINUTES` | Duration in minutes |
| `--snow-melt-mode 0\|1\|2` | Snow melt: 0=off, 1=on, 2=auto |

---

### `diagnostics` — hardware diagnostics

```bash
starlink diagnostics
starlink --json diagnostics
```

Returns hardware version, software version, country code, and all active alert flags.

---

### `reboot` — reboot the dish

```bash
starlink reboot
```

Prompts for confirmation before sending.

---

### `stow` / `unstow` — transport mode

```bash
starlink stow     # tilt dish flat for transport (Starlink Mini)
starlink unstow   # return to operational position
```

Both prompt for confirmation.

---

## Library usage

Import `StarlinkClient` directly in your own scripts.

```python
from starlink_telemetry import StarlinkClient

# One-shot query
with StarlinkClient() as c:
    s = c.get_status()
    print(f"Down: {s.downlink_throughput_bps / 1e6:.1f} Mbps")
    print(f"Up:   {s.uplink_throughput_bps / 1e6:.1f} Mbps")
    print(f"Ping: {s.pop_ping_latency_ms:.0f} ms  drop: {s.pop_ping_drop_rate * 100:.2f}%")
```

```python
# Custom host / port
client = StarlinkClient(host="192.168.100.1", port=9200, timeout=5.0)
client.connect()
cfg = client.get_config()
client.close()
```

```python
# Live monitoring loop
with StarlinkClient() as c:
    for snapshot in c.monitor(interval_s=5):
        print(f"{snapshot.downlink_throughput_bps / 1e6:.2f} Mbps")
```

```python
# History summary
with StarlinkClient() as c:
    summary = c.get_history_summary()
    print(f"Avg latency:    {summary['avg_latency_ms']:.1f} ms")
    print(f"Obstruction:    {summary['obstructed_fraction'] * 100:.1f}%")
    print(f"Avg downlink:   {summary['avg_downlink_bps'] / 1e6:.1f} Mbps")
```

### API reference

| Method | Returns | Description |
|--------|---------|-------------|
| `get_status()` | `DishStatus` | Current signal, throughput, alerts, pointing |
| `get_history()` | `DishHistory` | Full ring-buffer of per-second samples |
| `get_history_summary()` | `dict` | Averaged stats over the history window |
| `get_obstruction_map()` | `ObstructionMap` | Sky view bitmap |
| `get_config()` | `DishConfig` | Current dish configuration |
| `get_diagnostics()` | `DishDiagnostics` | Hardware diagnostics and alerts |
| `set_config(**kwargs)` | `None` | Update dish configuration |
| `reboot()` | `None` | Reboot the dish |
| `stow()` | `None` | Stow dish flat for transport |
| `unstow()` | `None` | Return dish to operational position |
| `monitor(interval_s)` | `Generator[DishStatus]` | Infinite stream of status snapshots |

---

## Networking notes

### Standard setup (Starlink router)

The dish is reachable at `192.168.100.1:9200` from any device on the Starlink router's LAN — no extra config needed.

### Bypass / direct connection (Starlink Mini)

When using the Mini's PoE cable in bypass mode (no Starlink router), your device needs a route to `192.168.100.0/24`.

```bash
# macOS — add a route via the interface connected to the dish (e.g. en5)
sudo route add -net 192.168.100.0/24 -interface en5
```

Use `--host` if your dish is at a different IP.

---

## Project structure

```
starlink-telemetry/
├── starlink_telemetry/
│   ├── __init__.py    # exports StarlinkClient
│   ├── client.py      # StarlinkClient + dataclasses for all API responses
│   └── cli.py         # click + rich terminal CLI
├── requirements.txt
└── pyproject.toml
```

---

## Credits

gRPC reflection approach inspired by [sparky8512/starlink-grpc-tools](https://github.com/sparky8512/starlink-grpc-tools), the definitive reference for the Starlink local gRPC API. Schema discovery powered by [yagrc](https://github.com/sparky8512/yagrc).
