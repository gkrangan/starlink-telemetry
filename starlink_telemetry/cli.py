"""Starlink telemetry CLI — rich terminal frontend for StarlinkClient."""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

import click
import grpc
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from starlink_telemetry.client import DISH_HOST, DISH_PORT, StarlinkClient

console = Console()

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def _make_client(host: str, port: int, timeout: float) -> StarlinkClient:
    c = StarlinkClient(host=host, port=port, timeout=timeout)
    c.connect()
    return c


def _handle_grpc_error(exc: grpc.RpcError) -> None:
    console.print(f"[bold red]gRPC error:[/] {exc.code().name}: {exc.details()}")
    sys.exit(1)


def _fmt_bps(bps: float) -> str:
    if bps >= 1e9:
        return f"{bps/1e9:.2f} Gbps"
    if bps >= 1e6:
        return f"{bps/1e6:.2f} Mbps"
    if bps >= 1e3:
        return f"{bps/1e3:.2f} Kbps"
    return f"{bps:.0f} bps"


def _fmt_uptime(s: int) -> str:
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def _status_panel(s) -> Panel:
    snr_label = "[green]yes[/]" if s.is_snr_above_noise_floor else "[red]no[/]"
    obst_label = "[red]yes[/]" if s.currently_obstructed else "[green]no[/]"

    # Signal / throughput
    sig = Table.grid(padding=(0, 2))
    sig.add_row("[bold]Uptime[/]", _fmt_uptime(s.uptime_s))
    sig.add_row("[bold]Latency[/]", f"{s.pop_ping_latency_ms:.1f} ms")
    sig.add_row("[bold]Ping drop[/]", f"{s.pop_ping_drop_rate*100:.2f}%")
    sig.add_row("[bold]SNR above noise[/]", snr_label)
    sig.add_row("[bold]Downlink[/]", _fmt_bps(s.downlink_throughput_bps))
    sig.add_row("[bold]Uplink[/]", _fmt_bps(s.uplink_throughput_bps))
    sig.add_row("[bold]Ethernet[/]", f"{s.eth_speed_mbps} Mbps")
    sig.add_row("[bold]Obstructed[/]", obst_label)
    sig.add_row("[bold]Obstruction %[/]", f"{s.fraction_obstruction_ratio*100:.1f}%")

    # Pointing / state
    ready_all = all([s.ready_cady, s.ready_scp, s.ready_l1l2, s.ready_xphy, s.ready_aap, s.ready_rf])
    point = Table.grid(padding=(0, 2))
    point.add_row("[bold]Azimuth[/]", f"{s.azimuth_deg:.1f}°")
    point.add_row("[bold]Elevation[/]", f"{s.elevation_deg:.1f}°")
    point.add_row("[bold]GPS valid[/]", "[green]yes[/]" if s.gps_valid else "[red]no[/]")
    point.add_row("[bold]GPS sats[/]", str(s.gps_sats))
    slots_val = s.seconds_to_first_nonempty_slot
    slots_str = "connected" if slots_val > 3600 else f"{slots_val:.1f}s"
    point.add_row("[bold]Slots in[/]", slots_str)
    point.add_row("[bold]Ready[/]", "[green]all[/]" if ready_all else f"cady={s.ready_cady} scp={s.ready_scp} l1l2={s.ready_l1l2} xphy={s.ready_xphy} aap={s.ready_aap} rf={s.ready_rf}")
    point.add_row("[bold]Stow req[/]", "[yellow]yes[/]" if s.stow_requested else "no")

    # Alerts
    active_alerts = list(s.alerts.keys())
    alert_subtitle = Text(
        "alerts: " + (", ".join(active_alerts) if active_alerts else "none"),
        style="red" if active_alerts else "green",
    )

    # Device info
    dev = Table.grid(padding=(0, 2))
    dev.add_row("[bold]ID[/]", s.id or "—")
    dev.add_row("[bold]Hardware[/]", s.hardware_version or "—")
    dev.add_row("[bold]Software[/]", s.software_version or "—")
    dev.add_row("[bold]Country[/]", s.country_code or "—")

    cols = Columns([
        Panel(sig, title="Signal & Throughput"),
        Panel(point, title="Pointing & State"),
        Panel(dev, title="Device"),
    ])

    return Panel(
        cols,
        title="[bold cyan]Starlink Dish Status[/]",
        subtitle=alert_subtitle,
    )


# ------------------------------------------------------------------
# CLI group
# ------------------------------------------------------------------

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--host", default=DISH_HOST, show_default=True, help="Dish IP address.")
@click.option("--port", default=DISH_PORT, show_default=True, help="gRPC port.")
@click.option("--timeout", default=10.0, show_default=True, help="Request timeout (s).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output raw JSON instead of formatted tables.")
@click.pass_context
def main(ctx, host, port, timeout, as_json):
    """Starlink telemetry CLI — pull data from your dish's local gRPC API.

    \b
    Examples:
      starlink status
      starlink watch --interval 2
      starlink history
      starlink --json status
      starlink --host 192.168.100.1 status

    \b
    Global flags go BEFORE the command:
      starlink --json status        (not: starlink status --json)
      starlink --host x.x.x.x status

    Run 'starlink COMMAND -h' for help on a specific command.
    """
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["timeout"] = timeout
    ctx.obj["as_json"] = as_json


@main.command(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def status(ctx):
    """Show current dish status.

    \b
    Displays: signal quality, throughput, latency, ping drop rate,
    pointing angles, GPS lock, obstruction %, alerts, and device info.

    \b
    Examples:
      starlink status
      starlink --json status
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        s = c.get_status()
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()

    if ctx.obj["as_json"]:
        click.echo(json.dumps(s.__dict__, indent=2))
        return

    console.print(_status_panel(s))


@main.command(context_settings=CONTEXT_SETTINGS)
@click.option("--interval", default=1.0, show_default=True, help="Refresh interval in seconds.")
@click.pass_context
def watch(ctx, interval):
    """Live auto-refreshing status dashboard.

    \b
    Press Ctrl-C to stop.

    \b
    Examples:
      starlink watch
      starlink watch --interval 2
      starlink watch --interval 0.5
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        with Live(console=console, refresh_per_second=max(1, int(1 / interval))) as live:
            for s in c.monitor(interval_s=interval):
                live.update(_status_panel(s))
    except KeyboardInterrupt:
        pass
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(context_settings=CONTEXT_SETTINGS)
@click.option("--raw", is_flag=True, default=False, help="Dump full per-second sample arrays instead of summary.")
@click.pass_context
def history(ctx, raw):
    """Show ping, latency, and throughput history (~12-hour window).

    \b
    The dish keeps ~45,000 one-second samples (roughly 12 hours).
    Default view shows averaged summary metrics.
    Use --raw to see every per-second data point.

    \b
    Examples:
      starlink history
      starlink history --raw
      starlink --json history
      starlink --json history --raw
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        if raw:
            h = c.get_history()
            data = h.__dict__.copy()
            data["outages"] = [o.__dict__ for o in h.outages]
            if ctx.obj["as_json"]:
                click.echo(json.dumps(data, indent=2))
            else:
                _print_table(data)
        else:
            summary = c.get_history_summary()
            if ctx.obj["as_json"]:
                click.echo(json.dumps(summary, indent=2))
            else:
                t = Table(title="History Summary", show_header=True)
                t.add_column("Metric", style="bold")
                t.add_column("Value")
                t.add_row("Samples", str(summary.get("samples", 0)))
                t.add_row("Avg ping drop", f"{summary.get('avg_ping_drop_rate', 0)*100:.3f}%")
                t.add_row("Avg latency", f"{summary.get('avg_latency_ms', 0):.1f} ms")
                t.add_row("Avg downlink", _fmt_bps(summary.get("avg_downlink_bps", 0)))
                t.add_row("Avg uplink", _fmt_bps(summary.get("avg_uplink_bps", 0)))
                t.add_row("Avg power draw", f"{summary.get('avg_power_in_w', 0):.1f} W")
                t.add_row("Outages", str(summary.get("outage_count", 0)))
                t.add_row("Total outage time", f"{summary.get('total_outage_ms', 0)/1000:.1f} s")
                console.print(t)
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(name="obstruction-map", context_settings=CONTEXT_SETTINGS)
@click.pass_context
def obstruction_map(ctx):
    """Print the sky obstruction map as an ASCII grid.

    \b
    █ = clear sky   ░ = partially obstructed   (space) = blocked / no data

    \b
    Examples:
      starlink obstruction-map
      starlink --json obstruction-map
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        m = c.get_obstruction_map()
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
        return
    finally:
        c.close()

    if ctx.obj["as_json"]:
        click.echo(json.dumps(m.__dict__, indent=2))
        return

    console.print(f"[bold]Obstruction map[/] {m.num_rows}×{m.num_cols}, min elevation {m.min_elevation_deg:.1f}°")
    if not m.snr:
        console.print("[yellow]No obstruction data available.[/]")
        return

    threshold = 0.5
    row_size = m.num_cols if m.num_cols > 0 else 1
    for row_idx in range(m.num_rows):
        row = m.snr[row_idx * row_size:(row_idx + 1) * row_size]
        line = "".join("█" if v > threshold else ("░" if v > 0 else " ") for v in row)
        console.print(line)


@main.command(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def config(ctx):
    """Show current dish configuration.

    \b
    Displays: power save schedule, snow melt mode,
    level-dish mode, and location request mode.

    \b
    Examples:
      starlink config
      starlink --json config
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        cfg = c.get_config()
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
        return
    finally:
        c.close()

    if ctx.obj["as_json"]:
        click.echo(json.dumps(cfg.__dict__, indent=2))
        return

    t = Table(title="Dish Configuration")
    t.add_column("Setting", style="bold")
    t.add_column("Value")
    for k, v in cfg.__dict__.items():
        t.add_row(k.replace("_", " ").title(), str(v))
    console.print(t)


@main.command("set-config", context_settings=CONTEXT_SETTINGS)
@click.option("--power-save/--no-power-save", default=None, help="Enable or disable power save mode.")
@click.option("--power-save-start", type=int, default=None, metavar="MINUTES", help="Power save start time (minutes from midnight UTC). e.g. 120 = 02:00 UTC.")
@click.option("--power-save-duration", type=int, default=None, metavar="MINUTES", help="Power save duration in minutes. e.g. 480 = 8 hours.")
@click.option("--snow-melt-mode", type=click.Choice(["0", "1", "2"]), default=None, help="Snow melt: 0=off, 1=on, 2=auto.")
@click.pass_context
def set_config(ctx, power_save, power_save_start, power_save_duration, snow_melt_mode):
    """Update dish configuration.

    \b
    Examples:
      starlink set-config --power-save
      starlink set-config --no-power-save
      starlink set-config --power-save-start 120 --power-save-duration 480
      starlink set-config --snow-melt-mode 2
    """
    if all(v is None for v in (power_save, power_save_start, power_save_duration, snow_melt_mode)):
        console.print("[yellow]No settings specified. Run 'starlink set-config -h' to see options.[/]")
        return

    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.set_config(
            power_save_mode=power_save,
            power_save_start_minutes=power_save_start,
            power_save_duration_minutes=power_save_duration,
            snow_melt_mode=int(snow_melt_mode) if snow_melt_mode is not None else None,
        )
        console.print("[green]Configuration updated.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(context_settings=CONTEXT_SETTINGS)
@click.confirmation_option(prompt="Reboot the dish?")
@click.pass_context
def reboot(ctx):
    """Reboot the dish.

    \b
    Examples:
      starlink reboot          (prompts for confirmation)
      starlink reboot --yes    (skips confirmation)
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.reboot()
        console.print("[green]Reboot command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(context_settings=CONTEXT_SETTINGS)
@click.confirmation_option(prompt="Stow the dish (tilt flat)?")
@click.pass_context
def stow(ctx):
    """Stow the dish flat for transport.

    \b
    Examples:
      starlink stow          (prompts for confirmation)
      starlink stow --yes    (skips confirmation)
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.stow()
        console.print("[green]Stow command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(context_settings=CONTEXT_SETTINGS)
@click.confirmation_option(prompt="Unstow the dish?")
@click.pass_context
def unstow(ctx):
    """Return the dish to its operational position.

    \b
    Examples:
      starlink unstow          (prompts for confirmation)
      starlink unstow --yes    (skips confirmation)
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.unstow()
        console.print("[green]Unstow command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def diagnostics(ctx):
    """Show hardware diagnostics and active alerts.

    \b
    Examples:
      starlink diagnostics
      starlink --json diagnostics
    """
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        d = c.get_diagnostics()
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
        return
    finally:
        c.close()

    if ctx.obj["as_json"]:
        click.echo(json.dumps(d.__dict__, indent=2))
        return

    t = Table(title="Dish Diagnostics")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    for k, v in d.__dict__.items():
        if k == "alerts":
            t.add_row("Active alerts", ", ".join(v.keys()) if v else "none")
        else:
            t.add_row(k.replace("_", " ").title(), str(v))
    console.print(t)


def _print_table(data: dict) -> None:
    t = Table()
    t.add_column("Key", style="bold")
    t.add_column("Value")
    for k, v in data.items():
        if isinstance(v, list) and len(v) > 10 and isinstance(v[0], float):
            t.add_row(k, f"[{v[0]:.4f}, {v[1]:.4f}, ... ({len(v)} samples)]")
        elif isinstance(v, list) and len(v) > 5 and isinstance(v[0], dict):
            t.add_row(k, f"({len(v)} entries) — use --json to see full detail")
        else:
            t.add_row(k, str(v))
    console.print(t)


if __name__ == "__main__":
    main()
