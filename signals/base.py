"""Shared SignalResult dataclass for all signal modules.

This is the single source of truth for the SignalResult contract
described in signals/CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SignalResult:
    """A single signal observation returned by any fetch() function.

    Fields:
        signal_name: Identifier like "wastewater_iav_level" or "flusurv_rate".
        epiweek: CDC MMWR epiweek integer (e.g. 202605).
        value: Normalized signal value.
        raw_value: Original value from source.
        unit: Measurement unit (e.g. "copies/mL/PMMoV", "percent").
        geography: Geographic scope ("national", state FIPS, or site ID).
        fetched_at: ISO timestamp of when the data was pulled.
        source_url: URL the data was pulled from.
        metadata: Any extra info (version, revision_number, etc.).
    """
    signal_name: str
    epiweek: int
    value: float
    raw_value: float
    unit: str
    geography: str
    fetched_at: str
    source_url: str
    metadata: dict = field(default_factory=dict)
