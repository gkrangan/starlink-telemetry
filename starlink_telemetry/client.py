"""StarlinkClient — full gRPC API wrapper for the Starlink dish."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

import grpc

DISH_HOST = "192.168.100.1"
DISH_PORT = 9200
DEFAULT_TIMEOUT = 10.0


def _lazy_imports():
    """Import proto stubs lazily so the module loads even before setup_protos runs."""
    try:
        from starlink_telemetry.proto.spacex.api.device import (  # type: ignore[import]
            device_pb2,
            device_pb2_grpc,
            dish_pb2,
        )
        return device_pb2, device_pb2_grpc, dish_pb2
    except ImportError as exc:
        raise RuntimeError(
            "Proto stubs not found. Run: python scripts/setup_protos.py"
        ) from exc


@dataclass
class DishStatus:
    """Parsed dish status snapshot."""

    state: str
    uptime_s: int
    snr_above_noise_floor: float
    pop_ping_drop_rate: float
    pop_ping_latency_ms: float
    downlink_throughput_bps: float
    uplink_throughput_bps: float
    azimuth_deg: float
    elevation_deg: float
    seconds_to_first_nonempty_slot: float
    gps_valid: bool
    gps_sats: int
    # Alerts
    alert_motors_stuck: bool
    alert_thermal_throttle: bool
    alert_thermal_shutdown: bool
    alert_mast_not_near_vertical: bool
    alert_unexpected_location: bool
    alert_slow_ethernet_speeds: bool
    alert_roaming: bool
    alert_install_pending: bool
    alert_is_heating: bool
    # Obstruction
    fraction_obstruction_ratio: float
    valid_s: int
    # Device info
    id: str
    hardware_version: str
    software_version: str
    country_code: str
    utc_offset_s: int


@dataclass
class DishHistory:
    """Parsed history ring-buffer (up to ~12 hours at 1-second resolution)."""

    current: int
    pop_ping_drop_rate: list[float] = field(default_factory=list)
    pop_ping_latency_ms: list[float] = field(default_factory=list)
    downlink_throughput_bps: list[float] = field(default_factory=list)
    uplink_throughput_bps: list[float] = field(default_factory=list)
    snr: list[float] = field(default_factory=list)
    scheduled: list[bool] = field(default_factory=list)
    obstructed: list[bool] = field(default_factory=list)
    no_sats: list[bool] = field(default_factory=list)


@dataclass
class ObstructionMap:
    """Obstruction map bitmap."""

    num_rows: int
    num_cols: int
    min_elevation_deg: float
    snr: list[float] = field(default_factory=list)


@dataclass
class DishConfig:
    """Dish configuration."""

    snow_melt_mode: int
    location_request_mode: int
    level_dish_mode: int
    power_save_start_minutes: int
    power_save_duration_minutes: int
    power_save_mode: bool
    apply_snow_melt_mode: bool
    apply_power_save_start_minutes: bool
    apply_power_save_duration_minutes: bool
    apply_power_save_mode: bool


@dataclass
class DishDiagnostics:
    """Hardware diagnostics."""

    id: str
    hardware_version: str
    software_version: str
    country_code: str
    utc_offset_s: int
    # Connectivity
    connected: bool
    # Dishy alerts as a flat dict
    alerts: dict[str, bool] = field(default_factory=dict)


class StarlinkClient:
    """
    Full gRPC client for the Starlink dish local API.

    Connects to the dish at 192.168.100.1:9200 (or a custom host/port).
    The dish must be reachable on your local network — the Starlink Mini
    typically bridges its subnet when using the Starlink router bypass cable
    or when bypassing via the app.

    Usage:
        client = StarlinkClient()
        status = client.get_status()
        print(status.downlink_throughput_bps)

        # Or use as a context manager:
        with StarlinkClient() as c:
            history = c.get_history()
    """

    def __init__(
        self,
        host: str = DISH_HOST,
        port: int = DISH_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._channel: Optional[grpc.Channel] = None
        self._stub = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the gRPC channel."""
        device_pb2, device_pb2_grpc, dish_pb2 = _lazy_imports()
        self._device_pb2 = device_pb2
        self._device_pb2_grpc = device_pb2_grpc
        self._dish_pb2 = dish_pb2
        self._channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        self._stub = device_pb2_grpc.DeviceStub(self._channel)

    def close(self) -> None:
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> "StarlinkClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _ensure_connected(self) -> None:
        if self._stub is None:
            self.connect()

    def _handle(self, request):
        """Send a single ToDevice request and return the response."""
        self._ensure_connected()
        return self._stub.Handle(  # type: ignore[union-attr]
            iter([request]),
            timeout=self.timeout,
        )

    @contextmanager
    def _stream(self) -> Generator:
        """Yield the stub for use in streaming scenarios."""
        self._ensure_connected()
        yield self._stub

    # ------------------------------------------------------------------
    # Core API — read operations
    # ------------------------------------------------------------------

    def get_status(self) -> DishStatus:
        """Return current dish status including signal, throughput, and alerts."""
        req = self._device_pb2.ToDevice(
            get_status=self._dish_pb2.DishGetStatusRequest()
        )
        resp = next(self._handle(req))
        s = resp.dish_get_status

        dev = s.device_info
        alerts = s.alerts

        return DishStatus(
            state=s.state.Name(s.state) if hasattr(s.state, "Name") else str(s.state),
            uptime_s=s.device_state.uptime_s,
            snr_above_noise_floor=s.snr_above_noise_floor,
            pop_ping_drop_rate=s.pop_ping_drop_rate,
            pop_ping_latency_ms=s.pop_ping_latency_ms,
            downlink_throughput_bps=s.downlink_throughput_bps,
            uplink_throughput_bps=s.uplink_throughput_bps,
            azimuth_deg=s.boresight_azimuth_deg,
            elevation_deg=s.boresight_elevation_deg,
            seconds_to_first_nonempty_slot=s.seconds_to_first_nonempty_slot,
            gps_valid=s.gps_stats.gps_valid,
            gps_sats=s.gps_stats.gps_sats,
            alert_motors_stuck=alerts.motors_stuck,
            alert_thermal_throttle=alerts.thermal_throttle,
            alert_thermal_shutdown=alerts.thermal_shutdown,
            alert_mast_not_near_vertical=alerts.mast_not_near_vertical,
            alert_unexpected_location=alerts.unexpected_location,
            alert_slow_ethernet_speeds=alerts.slow_ethernet_speeds,
            alert_roaming=alerts.roaming,
            alert_install_pending=alerts.install_pending,
            alert_is_heating=alerts.is_heating,
            fraction_obstruction_ratio=s.obstruction_stats.fraction_obstructed,
            valid_s=s.obstruction_stats.valid_s,
            id=dev.id,
            hardware_version=dev.hardware_version,
            software_version=dev.software_version,
            country_code=dev.country_code,
            utc_offset_s=dev.utc_offset_s,
        )

    def get_history(self) -> DishHistory:
        """Return the history ring-buffer (~12 hours at 1-second resolution)."""
        req = self._device_pb2.ToDevice(
            get_history=self._dish_pb2.DishGetHistoryRequest()
        )
        resp = next(self._handle(req))
        h = resp.dish_get_history

        return DishHistory(
            current=h.current,
            pop_ping_drop_rate=list(h.pop_ping_drop_rate),
            pop_ping_latency_ms=list(h.pop_ping_latency_ms),
            downlink_throughput_bps=list(h.downlink_throughput_bps),
            uplink_throughput_bps=list(h.uplink_throughput_bps),
            snr=list(h.snr),
            scheduled=list(h.scheduled),
            obstructed=list(h.obstructed),
            no_sats=list(h.no_sats),
        )

    def get_obstruction_map(self) -> ObstructionMap:
        """Return the obstruction map (sky view bitmap)."""
        req = self._device_pb2.ToDevice(
            get_obstruction_map=self._dish_pb2.DishGetObstructionMapRequest()
        )
        resp = next(self._handle(req))
        m = resp.dish_get_obstruction_map

        return ObstructionMap(
            num_rows=m.num_rows,
            num_cols=m.num_cols,
            min_elevation_deg=m.min_elevation_deg,
            snr=list(m.snr),
        )

    def get_config(self) -> DishConfig:
        """Return current dish configuration."""
        req = self._device_pb2.ToDevice(
            dish_get_config=self._dish_pb2.DishGetConfigRequest()
        )
        resp = next(self._handle(req))
        c = resp.dish_get_config.dish_config

        return DishConfig(
            snow_melt_mode=c.snow_melt_mode,
            location_request_mode=c.location_request_mode,
            level_dish_mode=c.level_dish_mode,
            power_save_start_minutes=c.power_save_start_minutes,
            power_save_duration_minutes=c.power_save_duration_minutes,
            power_save_mode=c.power_save_mode,
            apply_snow_melt_mode=c.apply_snow_melt_mode,
            apply_power_save_start_minutes=c.apply_power_save_start_minutes,
            apply_power_save_duration_minutes=c.apply_power_save_duration_minutes,
            apply_power_save_mode=c.apply_power_save_mode,
        )

    def get_diagnostics(self) -> DishDiagnostics:
        """Return hardware diagnostics."""
        req = self._device_pb2.ToDevice(
            get_diagnostics=self._dish_pb2.DishGetDiagnosticsRequest()
        )
        resp = next(self._handle(req))
        d = resp.dish_get_diagnostics
        dev = d.id

        alerts: dict[str, bool] = {}
        for descriptor in d.alerts.DESCRIPTOR.fields:
            val = getattr(d.alerts, descriptor.name, False)
            if val:
                alerts[descriptor.name] = val

        return DishDiagnostics(
            id=dev.hardware_version,  # diagnostics DeviceInfo differs slightly
            hardware_version=dev.hardware_version if hasattr(dev, "hardware_version") else "",
            software_version=dev.software_version if hasattr(dev, "software_version") else "",
            country_code=dev.country_code if hasattr(dev, "country_code") else "",
            utc_offset_s=dev.utc_offset_s if hasattr(dev, "utc_offset_s") else 0,
            connected=d.wifi_config.boot_count > 0 if hasattr(d, "wifi_config") else False,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def get_history_summary(self) -> dict:
        """Return averaged stats over the available history window."""
        h = self.get_history()
        n = len(h.pop_ping_drop_rate)
        if n == 0:
            return {}

        def _avg(lst: list) -> float:
            return sum(lst) / len(lst) if lst else 0.0

        scheduled = [v for v, s in zip(h.pop_ping_drop_rate, h.scheduled) if s]
        obstructed_count = sum(1 for v in h.obstructed if v)
        no_sats_count = sum(1 for v in h.no_sats if v)
        latency_valid = [v for v in h.pop_ping_latency_ms if v > 0]

        return {
            "samples": n,
            "avg_ping_drop_rate": _avg(h.pop_ping_drop_rate),
            "avg_ping_drop_rate_scheduled": _avg(scheduled) if scheduled else 0.0,
            "avg_latency_ms": _avg(latency_valid),
            "avg_downlink_bps": _avg(h.downlink_throughput_bps),
            "avg_uplink_bps": _avg(h.uplink_throughput_bps),
            "obstructed_fraction": obstructed_count / n,
            "no_sats_fraction": no_sats_count / n,
        }

    # ------------------------------------------------------------------
    # Control operations
    # ------------------------------------------------------------------

    def reboot(self) -> None:
        """Reboot the dish."""
        req = self._device_pb2.ToDevice(
            reboot=self._dish_pb2.DishRebootRequest()
        )
        next(self._handle(req))

    def stow(self) -> None:
        """Stow the dish (tilt flat for transport)."""
        req = self._device_pb2.ToDevice(
            dish_stow=self._dish_pb2.DishStowRequest(unstow=False)
        )
        next(self._handle(req))

    def unstow(self) -> None:
        """Unstow the dish (return to operational position)."""
        req = self._device_pb2.ToDevice(
            dish_stow=self._dish_pb2.DishStowRequest(unstow=True)
        )
        next(self._handle(req))

    def set_config(
        self,
        *,
        power_save_mode: Optional[bool] = None,
        power_save_start_minutes: Optional[int] = None,
        power_save_duration_minutes: Optional[int] = None,
        snow_melt_mode: Optional[int] = None,
    ) -> None:
        """Update dish configuration. Only provided fields are changed."""
        cfg = self._dish_pb2.DishConfig()

        if power_save_mode is not None:
            cfg.power_save_mode = power_save_mode
            cfg.apply_power_save_mode = True

        if power_save_start_minutes is not None:
            cfg.power_save_start_minutes = power_save_start_minutes
            cfg.apply_power_save_start_minutes = True

        if power_save_duration_minutes is not None:
            cfg.power_save_duration_minutes = power_save_duration_minutes
            cfg.apply_power_save_duration_minutes = True

        if snow_melt_mode is not None:
            cfg.snow_melt_mode = snow_melt_mode
            cfg.apply_snow_melt_mode = True

        req = self._device_pb2.ToDevice(
            dish_set_config=self._dish_pb2.DishSetConfigRequest(dish_config=cfg)
        )
        next(self._handle(req))

    # ------------------------------------------------------------------
    # Live monitoring
    # ------------------------------------------------------------------

    def monitor(self, interval_s: float = 1.0) -> Generator[DishStatus, None, None]:
        """Yield DishStatus snapshots at the given interval (seconds) forever."""
        while True:
            yield self.get_status()
            time.sleep(interval_s)
