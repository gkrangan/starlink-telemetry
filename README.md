# starlink-telemetry

A Python library and CLI for pulling real-time telemetry, stats, and diagnostics from your **Starlink dish** via its local gRPC API. Works with all current hardware including the **Starlink Mini**.

---

## How it works

Every Starlink dish exposes a private gRPC service at `192.168.100.1:9200` on your local network. This tool talks directly to that endpoint — no Starlink account, no cloud, no internet required — using the same protobuf API that the official Starlink app uses.

---

## Requirements

- Python 3.9+
- Starlink dish reachable at `192.168.100.1` (standard setup) or a custom IP
- pip packages: `grpcio`, `grpcio-tools`, `protobuf`, `click`, `rich`, `requests`

---

## Installation

```bash
git clone https://github.com/gkrangan/starlink-telemetry.git
cd starlink-telemetry
pip install -r requirements.txt
pip install -e .
```

### Generate gRPC stubs (required before first use)

The proto definitions are sourced from [sparky8512/starlink-grpc-tools](https://github.com/sparky8512/starlink-grpc-tools) and compiled locally:

```bash
python scripts/setup_protos.py
```

This downloads the `.proto` files and generates Python stubs into `starlink_telemetry/proto/`. Only needs to be run once (or again after a firmware update changes the API).

---

## CLI Usage

```
starlink [OPTIONS] COMMAND [ARGS]...
```

### Global options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `192.168.100.1` | Dish IP address |
| `--port` | `9200` | gRPC port |
| `--timeout` | `10.0` | Request timeout in seconds |
| `--json` | off | Output raw JSON instead of formatted tables |

---

### `status` — current dish snapshot

```bash
starlink status
starlink --json status
```

Displays:
- Dish state and uptime
- Downlink / uplink throughput (Mbps)
- Ping latency and drop rate
- SNR above noise floor
- Dish pointing (azimuth, elevation)
- GPS validity and satellite count
- Obstruction percentage
- Active alerts (thermal, motors, roaming, etc.)
- Device ID, hardware and software versions

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
starlink history                # averaged summary (~12-hour window)
starlink history --raw          # full per-second sample arrays
starlink --json history --raw   # pipe raw arrays to jq, etc.
```

The dish maintains a ring buffer of ~45,000 one-second samples (roughly 12 hours). The summary view averages these into a single report. The `--raw` flag dumps every array.

Summary metrics:
- Total samples in window
- Average ping drop rate (all slots + scheduled-only)
- Average latency (ms)
- Average downlink / uplink throughput
- Fraction of time obstructed or without satellites

---

### `obstruction-map` — sky view

```bash
starlink obstruction-map
```

Renders the dish's sky obstruction bitmap as an ASCII grid. Filled blocks (`█`) represent clear sky; light blocks (`░`) represent partially obstructed cells; spaces are blocked/no-data cells.

---

### `config` — dish configuration

```bash
starlink config
starlink --json config
```

Shows the current dish configuration: power save schedule, snow melt mode, level-dish mode, and location request mode.

---

### `set-config` — update configuration

```bash
# Enable power save mode, 02:00–10:00 UTC daily
starlink set-config --power-save --power-save-start 120 --power-save-duration 480

# Disable power save
starlink set-config --no-power-save

# Enable snow melt (0=off, 1=on, 2=auto)
starlink set-config --snow-melt-mode 2
```

| Option | Description |
|--------|-------------|
| `--power-save / --no-power-save` | Toggle power save mode |
| `--power-save-start MINUTES` | Start time (minutes from midnight UTC) |
| `--power-save-duration MINUTES` | Duration of power save window |
| `--snow-melt-mode 0\|1\|2` | Snow melt: 0=off, 1=on, 2=auto |

---

### `diagnostics` — hardware diagnostics

```bash
starlink diagnostics
starlink --json diagnostics
```

Returns hardware version, software version, country code, and a full list of active alert flags.

---

### `reboot` — reboot the dish

```bash
starlink reboot
```

Prompts for confirmation before sending the reboot command.

---

### `stow` / `unstow` — transport mode

```bash
starlink stow     # tilt dish flat for transport (Starlink Mini)
starlink unstow   # return to operational pointing
```

Both commands prompt for confirmation.

---

## Library Usage

Import `StarlinkClient` directly for use in your own scripts or applications.

```python
from starlink_telemetry import StarlinkClient

# One-shot query
with StarlinkClient() as c:
    s = c.get_status()
    print(f"Down: {s.downlink_throughput_bps/1e6:.1f} Mbps")
    print(f"Up:   {s.uplink_throughput_bps/1e6:.1f} Mbps")
    print(f"Ping: {s.pop_ping_latency_ms:.0f} ms  drop: {s.pop_ping_drop_rate*100:.2f}%")
```

```python
# Custom host / port
client = StarlinkClient(host="192.168.1.1", port=9200, timeout=5.0)
client.connect()
cfg = client.get_config()
client.close()
```

```python
# Live monitoring loop
with StarlinkClient() as c:
    for snapshot in c.monitor(interval_s=5):
        bps = snapshot.downlink_throughput_bps
        print(f"{bps/1e6:.2f} Mbps")
```

```python
# History summary
with StarlinkClient() as c:
    summary = c.get_history_summary()
    print(f"Avg latency: {summary['avg_latency_ms']:.1f} ms")
    print(f"Obstruction: {summary['obstructed_fraction']*100:.1f}%")
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
| `stow()` | `None` | Stow dish for transport |
| `unstow()` | `None` | Unstow dish to operational position |
| `monitor(interval_s)` | `Generator[DishStatus]` | Infinite stream of status snapshots |

---

## Networking notes

### Standard setup (Starlink router)

The dish is always reachable at `192.168.100.1:9200` from any device on your Starlink router's LAN — no extra configuration needed.

### Bypass / direct connection (Starlink Mini)

When using the Starlink Mini's PoE cable in bypass mode (no Starlink router), your device needs a route to `192.168.100.0/24`. Add a static route to that subnet via the interface connected to the dish, or use `--host` if your network topology differs.

```bash
# macOS — add route via the interface connected to the dish (e.g. en5)
sudo route add -net 192.168.100.0/24 -interface en5
```

---

## Project structure

```
starlink-telemetry/
├── starlink_telemetry/
│   ├── __init__.py          # exports StarlinkClient
│   ├── client.py            # StarlinkClient + dataclasses
│   ├── cli.py               # click + rich CLI
│   └── proto/               # generated gRPC stubs (after setup_protos.py)
├── scripts/
│   └── setup_protos.py      # downloads & compiles proto files
├── requirements.txt
└── pyproject.toml
```

---

## Credits

Proto definitions sourced from [sparky8512/starlink-grpc-tools](https://github.com/sparky8512/starlink-grpc-tools), the definitive reference for the Starlink local gRPC API.
