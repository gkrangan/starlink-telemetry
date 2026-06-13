"""StarlinkClient — full gRPC API wrapper for the Starlink dish.

Uses yagrc server reflection: no proto files or codegen step required.
The dish itself advertises its schema at connect time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Generator, Optional

import grpc
from yagrc import reflector as yagrc_reflector

DISH_HOST = "192.168.100.1"
DISH_PORT = 9200
DEFAULT_TIMEOUT = 10.0

_SERVICE = "SpaceX.API.Device.Device"


@dataclass
class DishStatus:
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
    alert_motors_stuck: bool
    alert_thermal_throttle: bool
    alert_thermal_shutdown: bool
    alert_mast_not_near_vertical: bool
    alert_unexpected_location: bool
    alert_slow_ethernet_speeds: bool
    alert_roaming: bool
    alert_install_pending: bool
    alert_is_heating: bool
    fraction_obstruction_ratio: float
    valid_s: int
    id: str
    hardware_version: str
    software_version: str
    country_code: str
    utc_offset_s: int


@dataclass
class DishHistory:
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
    num_rows: int
    num_cols: int
    min_elevation_deg: float
    snr: list[float] = field(default_factory=list)


@dataclass
class DishConfig:
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
    hardware_version: str
    software_version: str
    country_code: str
    utc_offset_s: int
    alerts: dict[str, bool] = field(default_factory=dict)


class StarlinkClient:
    """
    Full gRPC client for the Starlink dish local API.

    Connects to the dish at 192.168.100.1:9200 using gRPC server reflection
    (yagrc) — no proto files or codegen step required.

    Usage:
        with StarlinkClient() as c:
            status = c.get_status()
            print(status.downlink_throughput_bps)

        # Or manage connection manually:
        client = StarlinkClient(host="192.168.100.1")
        client.connect()
        history = client.get_history()
        client.close()
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
        self._Request = None
        self._DishConfig = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open gRPC channel and load reflection schema from the dish."""
        self._channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        grc = yagrc_reflector.GrpcReflectionClient()
        try:
            grc.load_protocols(self._channel, symbols=[_SERVICE])
        except (yagrc_reflector.ServiceError, KeyError) as exc:
            self._channel.close()
            raise ConnectionError(
                f"Could not load gRPC schema from dish at {self.host}:{self.port}. "
                "Is the dish reachable?"
            ) from exc

        self._stub = grc.service_stub_class(_SERVICE)(self._channel)
        self._Request = grc.message_class("SpaceX.API.Device.Request")
        try:
            self._DishConfig = grc.message_class("SpaceX.API.Device.DishConfig")
        except KeyError:
            self._DishConfig = None

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

    def _request(self, **kwargs):
        """Send a Request message and return the response."""
        self._ensure_connected()
        req = self._Request(**kwargs)
        resp = self._stub.Handle(iter([req]), timeout=self.timeout)
        return next(resp)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_status(self) -> DishStatus:
        """Return current dish status: signal, throughput, alerts, pointing."""
        resp = self._request(get_status={})
        s = resp.dish_get_status
        alerts = s.alerts
        dev = s.device_info

        def _state_name(val):
            try:
                return type(val).Name(val)
            except Exception:
                return str(val)

        return DishStatus(
            state=_state_name(s.state),
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
        resp = self._request(get_history={})
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
        """Return the sky obstruction map bitmap."""
        resp = self._request(get_obstruction_map={})
        m = resp.dish_get_obstruction_map
        return ObstructionMap(
            num_rows=m.num_rows,
            num_cols=m.num_cols,
            min_elevation_deg=m.min_elevation_deg,
            snr=list(m.snr),
        )

    def get_config(self) -> DishConfig:
        """Return current dish configuration."""
        resp = self._request(dish_get_config={})
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
        resp = self._request(get_diagnostics={})
        d = resp.dish_get_diagnostics
        dev = d.id

        alerts: dict[str, bool] = {}
        for descriptor in d.alerts.DESCRIPTOR.fields:
            val = getattr(d.alerts, descriptor.name, False)
            if val:
                alerts[descriptor.name] = val

        return DishDiagnostics(
            hardware_version=getattr(dev, "hardware_version", ""),
            software_version=getattr(dev, "software_version", ""),
            country_code=getattr(dev, "country_code", ""),
            utc_offset_s=getattr(dev, "utc_offset_s", 0),
            alerts=alerts,
        )

    def get_history_summary(self) -> dict:
        """Return averaged stats over the available history window."""
        h = self.get_history()
        n = len(h.pop_ping_drop_rate)
        if n == 0:
            return {}

        def _avg(lst):
            return sum(lst) / len(lst) if lst else 0.0

        scheduled = [v for v, s in zip(h.pop_ping_drop_rate, h.scheduled) if s]
        latency_valid = [v for v in h.pop_ping_latency_ms if v > 0]
        obstructed_count = sum(1 for v in h.obstructed if v)
        no_sats_count = sum(1 for v in h.no_sats if v)

        return {
            "samples": n,
            "avg_ping_drop_rate": _avg(h.pop_ping_drop_rate),
            "avg_ping_drop_rate_scheduled": _avg(scheduled),
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
        self._request(reboot={})

    def stow(self) -> None:
        """Stow the dish flat for transport."""
        self._request(dish_stow={"unstow": False})

    def unstow(self) -> None:
        """Return the dish to operational position."""
        self._request(dish_stow={"unstow": True})

    def set_config(
        self,
        *,
        power_save_mode: Optional[bool] = None,
        power_save_start_minutes: Optional[int] = None,
        power_save_duration_minutes: Optional[int] = None,
        snow_melt_mode: Optional[int] = None,
    ) -> None:
        """Update dish configuration. Only provided fields are applied."""
        if self._DishConfig is None:
            raise RuntimeError("DishConfig message not available via reflection.")

        cfg_kwargs: dict = {}
        if power_save_mode is not None:
            cfg_kwargs["power_save_mode"] = power_save_mode
            cfg_kwargs["apply_power_save_mode"] = True
        if power_save_start_minutes is not None:
            cfg_kwargs["power_save_start_minutes"] = power_save_start_minutes
            cfg_kwargs["apply_power_save_start_minutes"] = True
        if power_save_duration_minutes is not None:
            cfg_kwargs["power_save_duration_minutes"] = power_save_duration_minutes
            cfg_kwargs["apply_power_save_duration_minutes"] = True
        if snow_melt_mode is not None:
            cfg_kwargs["snow_melt_mode"] = snow_melt_mode
            cfg_kwargs["apply_snow_melt_mode"] = True

        self._request(dish_set_config={"dish_config": self._DishConfig(**cfg_kwargs)})

    # ------------------------------------------------------------------
    # Live monitoring
    # ------------------------------------------------------------------

    def monitor(self, interval_s: float = 1.0) -> Generator[DishStatus, None, None]:
        """Yield DishStatus snapshots at the given interval forever."""
        while True:
            yield self.get_status()
            time.sleep(interval_s)
