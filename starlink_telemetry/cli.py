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
    # Signal / throughput
    sig = Table.grid(padding=(0, 2))
    sig.add_row("[bold]State[/]", s.state)
    sig.add_row("[bold]Uptime[/]", _fmt_uptime(s.uptime_s))
    sig.add_row("[bold]Latency[/]", f"{s.pop_ping_latency_ms:.1f} ms")
    sig.add_row("[bold]Ping drop[/]", f"{s.pop_ping_drop_rate*100:.2f}%")
    sig.add_row("[bold]SNR above noise[/]", f"{s.snr_above_noise_floor:.2f} dB")
    sig.add_row("[bold]Downlink[/]", _fmt_bps(s.downlink_throughput_bps))
    sig.add_row("[bold]Uplink[/]", _fmt_bps(s.uplink_throughput_bps))
    sig.add_row("[bold]Obstruction[/]", f"{s.fraction_obstruction_ratio*100:.1f}%")

    # Pointing
    point = Table.grid(padding=(0, 2))
    point.add_row("[bold]Azimuth[/]", f"{s.azimuth_deg:.1f}°")
    point.add_row("[bold]Elevation[/]", f"{s.elevation_deg:.1f}°")
    point.add_row("[bold]GPS valid[/]", "[green]yes[/]" if s.gps_valid else "[red]no[/]")
    point.add_row("[bold]GPS sats[/]", str(s.gps_sats))
    point.add_row("[bold]Slots in[/]", f"{s.seconds_to_first_nonempty_slot:.1f}s")

    # Alerts
    alert_fields = {
        "motors_stuck": s.alert_motors_stuck,
        "thermal_throttle": s.alert_thermal_throttle,
        "thermal_shutdown": s.alert_thermal_shutdown,
        "mast_not_near_vertical": s.alert_mast_not_near_vertical,
        "unexpected_location": s.alert_unexpected_location,
        "slow_ethernet": s.alert_slow_ethernet_speeds,
        "roaming": s.alert_roaming,
        "install_pending": s.alert_install_pending,
        "is_heating": s.alert_is_heating,
    }
    active = [k for k, v in alert_fields.items() if v]
    alert_text = Text(", ".join(active) if active else "none", style="red" if active else "green")

    alerts = Table.grid(padding=(0, 2))
    alerts.add_row("[bold]Active alerts[/]", alert_text)

    # Device info
    dev = Table.grid(padding=(0, 2))
    dev.add_row("[bold]ID[/]", s.id or "—")
    dev.add_row("[bold]Hardware[/]", s.hardware_version or "—")
    dev.add_row("[bold]Software[/]", s.software_version or "—")
    dev.add_row("[bold]Country[/]", s.country_code or "—")

    cols = Columns([
        Panel(sig, title="Signal & Throughput"),
        Panel(point, title="Pointing"),
        Panel(dev, title="Device"),
    ])

    return Panel(
        click.unstyle(str(cols)) if False else cols,  # keep rich renderables
        title="[bold cyan]Starlink Dish Status[/]",
        subtitle=alerts,
    )


# ------------------------------------------------------------------
# CLI group
# ------------------------------------------------------------------

@click.group()
@click.option("--host", default=DISH_HOST, show_default=True, help="Dish IP address.")
@click.option("--port", default=DISH_PORT, show_default=True, help="gRPC port.")
@click.option("--timeout", default=10.0, show_default=True, help="Request timeout (s).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output raw JSON.")
@click.pass_context
def main(ctx, host, port, timeout, as_json):
    """Starlink telemetry CLI — reads all data from your dish's local gRPC API."""
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["timeout"] = timeout
    ctx.obj["as_json"] = as_json


@main.command()
@click.pass_context
def status(ctx):
    """Show current dish status (signal, throughput, alerts, pointing)."""
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


@main.command()
@click.option("--interval", default=1.0, show_default=True, help="Refresh interval (s).")
@click.pass_context
def watch(ctx, interval):
    """Live-updating status display (Ctrl-C to stop)."""
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


@main.command()
@click.option(
    "--raw", is_flag=True, default=False, help="Dump raw sample arrays instead of summary."
)
@click.pass_context
def history(ctx, raw):
    """Show ping, latency, and throughput history (~12-hour window)."""
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        if raw:
            h = c.get_history()
            data = h.__dict__.copy()
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
                t.add_row("Avg ping drop (scheduled)", f"{summary.get('avg_ping_drop_rate_scheduled', 0)*100:.3f}%")
                t.add_row("Avg latency", f"{summary.get('avg_latency_ms', 0):.1f} ms")
                t.add_row("Avg downlink", _fmt_bps(summary.get("avg_downlink_bps", 0)))
                t.add_row("Avg uplink", _fmt_bps(summary.get("avg_uplink_bps", 0)))
                t.add_row("Obstructed fraction", f"{summary.get('obstructed_fraction', 0)*100:.2f}%")
                t.add_row("No-sats fraction", f"{summary.get('no_sats_fraction', 0)*100:.2f}%")
                console.print(t)
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command()
@click.pass_context
def obstruction_map(ctx):
    """Print the sky obstruction map as an ASCII grid."""
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


@main.command()
@click.pass_context
def config(ctx):
    """Show current dish configuration."""
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


@main.command("set-config")
@click.option("--power-save/--no-power-save", default=None, help="Enable/disable power save mode.")
@click.option("--power-save-start", type=int, default=None, help="Power save start (minutes from midnight UTC).")
@click.option("--power-save-duration", type=int, default=None, help="Power save duration (minutes).")
@click.option("--snow-melt-mode", type=int, default=None, help="Snow melt mode (0=off, 1=on, 2=auto).")
@click.pass_context
def set_config(ctx, power_save, power_save_start, power_save_duration, snow_melt_mode):
    """Update dish configuration."""
    if all(v is None for v in (power_save, power_save_start, power_save_duration, snow_melt_mode)):
        console.print("[yellow]No settings specified. Use --help to see options.[/]")
        return

    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.set_config(
            power_save_mode=power_save,
            power_save_start_minutes=power_save_start,
            power_save_duration_minutes=power_save_duration,
            snow_melt_mode=snow_melt_mode,
        )
        console.print("[green]Configuration updated.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command()
@click.confirmation_option(prompt="Reboot the dish?")
@click.pass_context
def reboot(ctx):
    """Reboot the dish."""
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.reboot()
        console.print("[green]Reboot command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command()
@click.confirmation_option(prompt="Stow the dish (tilt flat)?")
@click.pass_context
def stow(ctx):
    """Stow the dish for transport."""
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.stow()
        console.print("[green]Stow command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command()
@click.confirmation_option(prompt="Unstow the dish?")
@click.pass_context
def unstow(ctx):
    """Unstow the dish (return to operational position)."""
    c = _make_client(**{k: ctx.obj[k] for k in ("host", "port", "timeout")})
    try:
        c.unstow()
        console.print("[green]Unstow command sent.[/]")
    except grpc.RpcError as exc:
        _handle_grpc_error(exc)
    finally:
        c.close()


@main.command()
@click.pass_context
def diagnostics(ctx):
    """Show hardware diagnostics."""
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
        if isinstance(v, list) and len(v) > 10:
            t.add_row(k, f"[{v[0]:.4f}, {v[1]:.4f}, ... ({len(v)} samples)]")
        else:
            t.add_row(k, str(v))
    console.print(t)


if __name__ == "__main__":
    main()
