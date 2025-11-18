"""Data models for device information and settings."""

from dataclasses import dataclass


@dataclass
class SomeInfo:
    """Represents some information with various attributes."""

    s: int | None = None
    v: int | None = None
    bp: int | None = None
    bpr: int | None = None
    bi: int | None = None


@dataclass
class DeviceInformation:
    """Represents device information with various attributes."""

    ak: str | None = None
    fhs: int | None = None
    u: int | None = None
    wr: int | None = None
    ss: str | None = None
    t: str | None = None
    n: str | None = None
    tsc: int | None = None
    lcu: str | None = None
    lat: int | None = None
    lon: int | None = None
    cs: bool | None = None
    sr_h: int | None = None
    sr_m: int | None = None
    ss_h: int | None = None
    ss_m: int | None = None
    tz_o: int | None = None
    tz_i: int | None = None
    tz_dst: int | None = None
    c: bool | None = None
    ws: str | None = None
    rr: int | None = None
    hwm: str | None = None
    nhwv: int | None = None
    nswv: str | None = None
    b: SomeInfo | None = None


@dataclass
class Settings:
    """Represents device settings with various configuration attributes."""

    name: str | None = None
    tz_id: int | None = None
    auto_on_seconds: int | None = None
    auto_off_seconds: int | None = None
    enable_local_security: int | None = None
    vacation_mode: int | None = None
    state_after_powerloss: int | None = None
    disable_physical_button: int | None = None
    disable_433: int | None = None
    disable_multi_press: int | None = None
    disable_network_ctrl: int | None = None
    disable_led: int | None = None
    disable_on_transmitters: int | None = None
    disable_off_transmitters: int | None = None
    dimmer_edge: int | None = None
    blink_on_433_on: int | None = None
    button_type: int | None = None
    diy_mode: int | None = None
    toggle_433: int | None = None
    position_man_set: int | None = None
    dimmer_on_start_level: int | None = None
    dimmer_off_level: int | None = None
    dimmer_min_dim: int | None = None
    remote_log: int | None = None
    notifcation_on: int | None = None
    notifcation_off: int | None = None
