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

## Installation (one-time)

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

## Every time you want to use it

Open a terminal and run these exact three commands:

```bash
cd /Users/gkrangan/Documents/vscode-projects/starlink-telemetry
source .venv/bin/activate
starlink status
```

> **Important:** Always use `source .venv/bin/activate` — not `.venv/bin/activate` on its own.
> The `source` command loads the virtual environment into your current shell session.
> Running it without `source` will give a "permission denied" error and won't work.

Your prompt will change to show `(.venv)` when the environment is active.
To deactivate when you're done: type `deactivate`.

---

## Commands

### Quick reference

| Command | What it does |
|---------|-------------|
| `starlink status` | Current signal, throughput, latency, alerts |
| `starlink watch` | Live auto-refreshing status (Ctrl-C to stop) |
| `starlink watch --interval 2` | Refresh every 2 seconds |
| `starlink history` | Averaged stats over the last ~12 hours |
| `starlink history --raw` | Full per-second sample arrays |
| `starlink obstruction-map` | ASCII sky obstruction grid |
| `starlink config` | Show dish configuration |
| `starlink set-config --power-save` | Enable power save mode |
| `starlink set-config --no-power-save` | Disable power save mode |
| `starlink set-config --snow-melt-mode 2` | Snow melt: 0=off 1=on 2=auto |
| `starlink set-config --power-save-start 120 --power-save-duration 480` | Power save 02:00–10:00 UTC |
| `starlink diagnostics` | Hardware diagnostics and active alerts |
| `starlink reboot` | Reboot the dish (asks for confirmation) |
| `starlink reboot --yes` | Reboot without confirmation prompt |
| `starlink stow` | Tilt dish flat for transport (asks for confirmation) |
| `starlink stow --yes` | Stow without confirmation prompt |
| `starlink unstow` | Return dish to operational position |

### Global options (go before the command)

```bash
starlink --json status          # raw JSON output instead of formatted table
starlink --host 192.168.1.1 status  # use a different dish IP
starlink --timeout 5 status     # shorter timeout (seconds)
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `192.168.100.1` | Dish IP address |
| `--port` | `9200` | gRPC port |
| `--timeout` | `10.0` | Request timeout (seconds) |
| `--json` | off | Output raw JSON instead of formatted tables |

---

### `status`

```bash
starlink status
starlink --json status
```

Displays signal quality, throughput, latency, ping drop rate, pointing angles, GPS, obstruction percentage, active alerts, and device info.

**Example output:**
```
╭──────────────────────────── Starlink Dish Status ────────────────────────────╮
│ ╭──────────────────────── Signal & Throughput ────────────────────────╮      │
│ │ Uptime           1h 52m 39s                                         │      │
│ │ Latency          22.2 ms                                            │      │
│ │ Ping drop        0.00%                                              │      │
│ │ SNR above noise  yes                                                │      │
│ │ Downlink         655.48 Kbps                                        │      │
│ │ Uplink           65.00 Kbps                                         │      │
│ │ Ethernet         1000 Mbps                                          │      │
│ │ Obstructed       no                                                 │      │
│ │ Obstruction %    5.4%                                               │      │
│ ╰─────────────────────────────────────────────────────────────────────╯      │
│ ╭───────────────────────── Pointing & State ──────────────────────────╮      │
│ │ Azimuth    5.3°                                                     │      │
│ │ Elevation  68.7°                                                    │      │
│ │ GPS valid  yes                                                      │      │
│ │ GPS sats   18                                                       │      │
│ │ Slots in   connected                                                │      │
│ │ Ready      cady=False scp=True l1l2=True xphy=True aap=True rf=True │      │
│ │ Stow req   no                                                       │      │
│ ╰─────────────────────────────────────────────────────────────────────╯      │
│ ╭────────────────────────────── Device ───────────────────────────────╮      │
│ │ ID        ut41780985-c611791c-59a90bde                              │      │
│ │ Hardware  mini1_panda_prod1                                         │      │
│ │ Software  2026.06.02.mr80873                                        │      │
│ │ Country   US                                                        │      │
│ ╰─────────────────────────────────────────────────────────────────────╯      │
╰──────────────────────────────── alerts: none ────────────────────────────────╯
```

---

### `watch`

```bash
starlink watch
starlink watch --interval 2
```

Auto-refreshing status panel. Press `Ctrl-C` to stop.

| Option | Default | Description |
|--------|---------|-------------|
| `--interval` | `1.0` | Refresh interval in seconds |

---

### `history`

```bash
starlink history           # averaged summary (~12-hour window)
starlink history --raw     # full per-second sample arrays
starlink --json history    # JSON output
```

The dish maintains a ring buffer of ~45,000 one-second samples (roughly 12 hours). The summary view shows averaged metrics; `--raw` dumps every array.

| Option | Description |
|--------|-------------|
| `--raw` | Dump raw per-second sample arrays instead of summary |

---

### `obstruction-map`

```bash
starlink obstruction-map
```

Renders the dish's sky obstruction bitmap as an ASCII grid. Filled blocks (`█`) = clear sky, light blocks (`░`) = partially obstructed, spaces = blocked/no-data.

---

### `config`

```bash
starlink config
starlink --json config
```

Shows the current dish configuration: power save schedule, snow melt mode, level-dish mode, location request mode.

---

### `set-config`

```bash
starlink set-config --power-save
starlink set-config --no-power-save
starlink set-config --power-save-start 120 --power-save-duration 480
starlink set-config --snow-melt-mode 2
```

| Option | Description |
|--------|-------------|
| `--power-save / --no-power-save` | Enable or disable power save mode |
| `--power-save-start MINUTES` | Start time (minutes from midnight UTC, e.g. 120 = 02:00) |
| `--power-save-duration MINUTES` | Duration of power save window in minutes |
| `--snow-melt-mode 0\|1\|2` | 0 = off, 1 = on, 2 = auto |

---

### `diagnostics`

```bash
starlink diagnostics
starlink --json diagnostics
```

Returns hardware version, software version, country code, and all active alert flags.

---

### `reboot`

```bash
starlink reboot        # prompts for confirmation
starlink reboot --yes  # skips confirmation
```

---

### `stow` / `unstow`

```bash
starlink stow          # tilt dish flat for transport — prompts for confirmation
starlink stow --yes    # skips confirmation
starlink unstow        # return to operational position — prompts for confirmation
starlink unstow --yes  # skips confirmation
```

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
    print(f"Avg latency:  {summary['avg_latency_ms']:.1f} ms")
    print(f"Obstruction:  {summary['obstructed_fraction'] * 100:.1f}%")
    print(f"Avg downlink: {summary['avg_downlink_bps'] / 1e6:.1f} Mbps")
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
