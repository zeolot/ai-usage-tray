# -*- coding: utf-8 -*-
"""Data structures for usage events and aggregated model statistics."""

from typing import Dict, List, Optional


class UsageEvent(object):
    """A single model request record parsed from Codex or Antigravity logs."""

    __slots__ = (
        "source",
        "model",
        "timestamp",
        "uncached_input",
        "cached_input",
        "cache_write_input",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "duration_ms",
        "ttft_ms",
        "timed_tokens",
        "is_estimated_speed",
    )

    def __init__(
        self,
        source,             # type: str  # "codex" or "antigravity"
        model,              # type: str
        timestamp,          # type: float  # POSIX seconds (UTC)
        uncached_input=0,   # type: int
        cached_input=0,     # type: int
        cache_write_input=0,# type: int
        output_tokens=0,    # type: int
        reasoning_tokens=0, # type: int
        total_tokens=0,     # type: int
        duration_ms=None,   # type: Optional[float]
        ttft_ms=None,       # type: Optional[float]
        timed_tokens=0,     # type: int
        is_estimated_speed=False,  # type: bool
    ):
        self.source = source
        self.model = model
        self.timestamp = timestamp
        self.uncached_input = int(uncached_input or 0)
        self.cached_input = int(cached_input or 0)
        self.cache_write_input = int(cache_write_input or 0)
        self.output_tokens = int(output_tokens or 0)
        self.reasoning_tokens = int(reasoning_tokens or 0)
        self.total_tokens = int(
            total_tokens
            if total_tokens
            else (self.uncached_input + self.cached_input + self.output_tokens)
        )
        self.duration_ms = duration_ms
        self.ttft_ms = ttft_ms
        self.timed_tokens = int(timed_tokens or 0)
        self.is_estimated_speed = bool(is_estimated_speed)


class TimingSample(object):
    """Independent timing sample (e.g., Codex AgentMessage stream or task TTFT)."""

    __slots__ = (
        "source",
        "model",
        "timestamp",
        "tokens",
        "duration_ms",
        "ttft_ms",
        "is_estimated",
    )

    def __init__(
        self,
        source,            # type: str
        model,             # type: str
        timestamp,         # type: float
        tokens=0,          # type: int
        duration_ms=None,  # type: Optional[float]
        ttft_ms=None,      # type: Optional[float]
        is_estimated=False,# type: bool
    ):
        self.source = source
        self.model = model
        self.timestamp = timestamp
        self.tokens = int(tokens or 0)
        self.duration_ms = duration_ms
        self.ttft_ms = ttft_ms
        self.is_estimated = bool(is_estimated)


class ModelStats(object):
    """Aggregated statistics for one (source, model) or merged model row."""

    def __init__(self, model, sources=None):
        # type: (str, Optional[List[str]]) -> None
        self.model = model
        self.sources = set(sources or [])
        self.requests = 0
        self.uncached_input = 0
        self.cached_input = 0
        self.cache_write_input = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0

        # Speed aggregation
        self.timed_count = 0
        self.timed_tokens = 0
        self.timed_duration_ms = 0.0
        self.speed_is_estimated = False

        # TTFT aggregation
        self.ttft_count = 0
        self.ttft_total_ms = 0.0

        # Relative share (0..100) populated after aggregation
        self.share_pct = 0.0

    @property
    def total_input(self):
        # type: () -> int
        return self.uncached_input + self.cached_input

    @property
    def cache_hit_pct(self):
        # type: () -> Optional[float]
        if self.total_input <= 0:
            return None
        return (float(self.cached_input) / float(self.total_input)) * 100.0

    @property
    def tokens_per_sec(self):
        # type: () -> Optional[float]
        if self.timed_count <= 0 or self.timed_duration_ms <= 0 or self.timed_tokens <= 0:
            return None
        return float(self.timed_tokens) / (self.timed_duration_ms / 1000.0)

    @property
    def avg_ttft_sec(self):
        # type: () -> Optional[float]
        if self.ttft_count <= 0:
            return None
        return (self.ttft_total_ms / float(self.ttft_count)) / 1000.0


class SummaryStats(object):
    """Top-level summary for the currently selected filter."""

    def __init__(self):
        self.total_tokens = 0
        self.total_requests = 0
        self.total_cost_usd = 0.0
        self.total_uncached_input = 0
        self.total_cached_input = 0
        self.total_output_tokens = 0
        self.models = []  # type: List[ModelStats]
        self.source_totals = {"codex": 0, "antigravity": 0}  # type: Dict[str, int]
        self.source_requests = {"codex": 0, "antigravity": 0}  # type: Dict[str, int]

    @property
    def cache_hit_pct(self):
        # type: () -> Optional[float]
        total_in = self.total_uncached_input + self.total_cached_input
        if total_in <= 0:
            return None
        return (float(self.total_cached_input) / float(total_in)) * 100.0
