# -*- coding: utf-8 -*-
"""Incremental mtime-cached log collector for Codex and Antigravity."""

import calendar
import datetime
import glob
import json
import os
import time
from typing import Dict, List, Optional, Tuple

from .models import ModelStats, SummaryStats, TimingSample, UsageEvent
from .platform_utils import (
    get_antigravity_brain_dir,
    get_cache_dir,
    get_codex_sessions_dir,
)
from .pricing import PricingManager

CODEX_SESSIONS_DIR = get_codex_sessions_dir()
ANTIGRAVITY_BRAIN_DIR = get_antigravity_brain_dir()
CACHE_DIR = get_cache_dir()
AG_LIVE_TIMING_CACHE = os.path.join(CACHE_DIR, "ag_live_timings.json")


def _discover_codex_files(sessions_dir):
    # type: (str) -> List[str]
    """Find all Codex session .jsonl files cross-platform (Windows & Linux)."""
    if not sessions_dir or not os.path.isdir(sessions_dir):
        return []
    found = []  # type: List[str]
    for root, _dirs, files in os.walk(sessions_dir):
        for fn in files:
            if fn.endswith(".jsonl"):
                found.append(os.path.join(root, fn))
    return found


def _discover_antigravity_files(brain_dir):
    # type: (str) -> List[str]
    """Find all Antigravity transcript.jsonl files cross-platform."""
    if not brain_dir or not os.path.isdir(brain_dir):
        return []
    pattern = os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")
    return glob.glob(pattern)


def parse_iso_timestamp(ts_str):
    # type: (Optional[str]) -> Optional[float]
    """Parse ISO-8601 UTC/offset timestamps safely on Python 3.7+."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    s = ts_str.strip()
    if not s:
        return None
    try:
        # Handle trailing 'Z'
        if s.endswith("Z"):
            core = s[:-1]
            if "." in core:
                dt_part, frac_part = core.split(".", 1)
                frac_part = (frac_part[:6]).ljust(6, "0")
                dt = datetime.datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")
                return float(calendar.timegm(dt.timetuple())) + (int(frac_part) / 1000000.0)
            dt = datetime.datetime.strptime(core, "%Y-%m-%dT%H:%M:%S")
            return float(calendar.timegm(dt.timetuple()))

        # Handle explicit timezone offset like +08:00 or -05:00
        tz_sign = 0
        tz_idx = -1
        for sep in ("+", "-"):
            idx = s.rfind(sep)
            if idx > 10:
                tz_idx = idx
                tz_sign = 1 if sep == "+" else -1
                break

        if tz_idx > 0:
            core = s[:tz_idx]
            tz_str = s[tz_idx + 1:].replace(":", "")
            tz_h = int(tz_str[:2])
            tz_m = int(tz_str[2:4]) if len(tz_str) >= 4 else 0
            offset_sec = tz_sign * (tz_h * 3600 + tz_m * 60)
        else:
            core = s
            offset_sec = 0

        if "." in core:
            dt_part, frac_part = core.split(".", 1)
            frac_part = (frac_part[:6]).ljust(6, "0")
            dt = datetime.datetime.strptime(dt_part, "%Y-%m-%dT%H:%M:%S")
            base = float(calendar.timegm(dt.timetuple())) + (int(frac_part) / 1000000.0)
        else:
            dt = datetime.datetime.strptime(core, "%Y-%m-%dT%H:%M:%S")
            base = float(calendar.timegm(dt.timetuple()))
        return base - offset_sec
    except Exception:
        return None


def get_time_cutoff(time_range):
    # type: (str) -> Optional[float]
    """Return POSIX UTC cutoff timestamp for 'today', '7d', '30d', or 'all'."""
    if time_range == "all":
        return None
    now_local = datetime.datetime.now()
    if time_range == "today":
        midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return time.mktime(midnight.timetuple())
    if time_range == "7d":
        dt = (now_local - datetime.timedelta(days=6)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return time.mktime(dt.timetuple())
    if time_range == "30d":
        dt = (now_local - datetime.timedelta(days=29)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return time.mktime(dt.timetuple())
    return None


class UsageCollector(object):
    """Scans Codex and Antigravity local logs with per-file mtime caching."""

    def __init__(
        self,
        pricing_manager=None,                # type: Optional[PricingManager]
        codex_dir=None,                      # type: Optional[str]
        ag_brain_dir=None,                   # type: Optional[str]
    ):
        self.pricing = pricing_manager or PricingManager()
        self.codex_dir = codex_dir if codex_dir is not None else get_codex_sessions_dir()
        self.ag_brain_dir = ag_brain_dir if ag_brain_dir is not None else get_antigravity_brain_dir()

        # path -> (mtime, size, events, timings)
        self._codex_cache = {}  # type: Dict[str, Tuple[float, int, List[Tuple[Optional[str], UsageEvent]], List[TimingSample]]]
        self._ag_cache = {}     # type: Dict[str, Tuple[float, int, List[UsageEvent], List[TimingSample]]]

        # key "conv_id:step_index" -> duration_ms observed live for final AG replies
        self._ag_live_timings = self._load_ag_live_timings()
        self._ag_live_dirty = False
        self.last_refresh_ts = 0.0

    def _load_ag_live_timings(self):
        # type: () -> Dict[str, float]
        if os.path.isfile(AG_LIVE_TIMING_CACHE):
            try:
                with open(AG_LIVE_TIMING_CACHE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return {str(k): float(v) for k, v in data.items()}
            except Exception:
                pass
        return {}

    def _save_ag_live_timings(self):
        # type: () -> None
        if not self._ag_live_dirty:
            return
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            # Keep cache bounded to recent 5000 entries
            if len(self._ag_live_timings) > 5000:
                keys = list(self._ag_live_timings.keys())[-5000:]
                self._ag_live_timings = {k: self._ag_live_timings[k] for k in keys}
            with open(AG_LIVE_TIMING_CACHE, "w", encoding="utf-8") as fh:
                json.dump(self._ag_live_timings, fh)
            self._ag_live_dirty = False
        except Exception:
            pass

    def _parse_codex_file(self, path):
        # type: (str) -> Tuple[List[Tuple[Optional[str], UsageEvent]], List[TimingSample]]
        events = []   # type: List[Tuple[Optional[str], UsageEvent]]
        timings = []  # type: List[TimingSample]
        cur_model = None
        turn_models = {}  # type: Dict[str, str]
        file_mtime = os.path.getmtime(path)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue

                    ev_type = obj.get("type")
                    payload = obj.get("payload")
                    if not isinstance(payload, dict):
                        continue

                    ts = parse_iso_timestamp(obj.get("timestamp")) or file_mtime

                    if ev_type == "turn_context":
                        m = payload.get("model")
                        tid = payload.get("turn_id")
                        if m:
                            cur_model = str(m)
                            if tid:
                                turn_models[str(tid)] = cur_model

                    elif ev_type == "token_usage_record":
                        usage = payload.get("usage")
                        if not isinstance(usage, dict):
                            continue
                        tid = payload.get("turn_id")
                        model = (
                            turn_models.get(str(tid)) if tid else None
                        ) or cur_model or "codex-unknown"
                        resp_id = payload.get("response_id")

                        in_tok = int(usage.get("input_tokens") or 0)
                        cached_tok = int(usage.get("cached_input_tokens") or 0)
                        cache_write_tok = int(usage.get("cache_write_input_tokens") or 0)
                        out_tok = int(usage.get("output_tokens") or 0)
                        reason_tok = int(usage.get("reasoning_output_tokens") or 0)
                        total_tok = int(usage.get("total_tokens") or (in_tok + out_tok))
                        uncached_in = max(0, in_tok - cached_tok)

                        ev = UsageEvent(
                            source="codex",
                            model=model,
                            timestamp=ts,
                            uncached_input=uncached_in,
                            cached_input=cached_tok,
                            cache_write_input=cache_write_tok,
                            output_tokens=out_tok,
                            reasoning_tokens=reason_tok,
                            total_tokens=total_tok,
                        )
                        events.append((str(resp_id) if resp_id else None, ev))

                    elif ev_type == "event_msg":
                        ptype = payload.get("type")
                        tid = payload.get("turn_id")
                        model = (
                            turn_models.get(str(tid)) if tid else None
                        ) or cur_model or "codex-unknown"

                        if ptype == "item_completed":
                            item = payload.get("item")
                            if isinstance(item, dict) and item.get("type") == "AgentMessage":
                                tok = int(payload.get("content_token_count") or 0)
                                start_ms = payload.get("started_at_ms")
                                end_ms = payload.get("completed_at_ms")
                                if (
                                    tok > 0
                                    and start_ms is not None
                                    and end_ms is not None
                                    and end_ms > start_ms
                                ):
                                    dur_ms = float(end_ms - start_ms)
                                    # Filter extreme anomalies (>10 min for single message)
                                    if 50.0 <= dur_ms <= 600000.0:
                                        timings.append(
                                            TimingSample(
                                                source="codex",
                                                model=model,
                                                timestamp=ts,
                                                tokens=tok,
                                                duration_ms=dur_ms,
                                                is_estimated=False,
                                            )
                                        )

                        elif ptype == "task_complete":
                            ttft_ms = payload.get("time_to_first_token_ms")
                            if ttft_ms is not None:
                                try:
                                    ttft_val = float(ttft_ms)
                                    if 0.0 <= ttft_val <= 600000.0:
                                        timings.append(
                                            TimingSample(
                                                source="codex",
                                                model=model,
                                                timestamp=ts,
                                                tokens=0,
                                                duration_ms=None,
                                                ttft_ms=ttft_val,
                                                is_estimated=False,
                                            )
                                        )
                                except Exception:
                                    pass
        except OSError:
            pass

        return events, timings

    def _parse_antigravity_file(self, path, file_mtime):
        # type: (str, float) -> Tuple[List[UsageEvent], List[TimingSample]]
        events = []   # type: List[UsageEvent]
        timings = []  # type: List[TimingSample]
        rows = []     # type: List[dict]

        # Extract conversation ID from .../brain/<conv_id>/.system_generated/logs/transcript.jsonl
        parts = path.replace("\\", "/").split("/")
        conv_id = parts[-4] if len(parts) >= 4 else os.path.basename(path)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            rows.append(obj)
                    except Exception:
                        continue
        except OSError:
            return events, timings

        n = len(rows)
        for idx, obj in enumerate(rows):
            if obj.get("type") != "PLANNER_RESPONSE":
                continue

            model = obj.get("model")
            in_tok = int(obj.get("input_tokens") or 0)
            cache_read = int(obj.get("cache_read_tokens") or 0)
            out_tok = int(obj.get("output_tokens") or 0)
            if not model and in_tok == 0 and cache_read == 0 and out_tok == 0:
                continue

            model_name = str(model or "antigravity-unknown")
            ts = parse_iso_timestamp(obj.get("created_at")) or file_mtime
            total_tok = in_tok + cache_read + out_tok

            ev = UsageEvent(
                source="antigravity",
                model=model_name,
                timestamp=ts,
                uncached_input=in_tok,
                cached_input=cache_read,
                cache_write_input=0,
                output_tokens=out_tok,
                reasoning_tokens=0,
                total_tokens=total_tok,
            )
            events.append(ev)

            # Estimate end-to-end duration when possible
            if out_tok > 0:
                dur_ms = None  # type: Optional[float]
                step_key = "{}:{}".format(conv_id, obj.get("step_index", idx))

                if idx + 1 < n:
                    nxt = rows[idx + 1]
                    # Only use next step timestamp if it's an automatic tool/system step,
                    # NOT a user reply (which includes user think/type time).
                    if nxt.get("type") != "USER_INPUT" and nxt.get("source") != "USER_EXPLICIT":
                        nxt_ts = parse_iso_timestamp(nxt.get("created_at"))
                        if nxt_ts is not None:
                            dt = nxt_ts - ts
                            if 0.5 <= dt <= 300.0:
                                dur_ms = dt * 1000.0

                if dur_ms is None:
                    # Check cached live observation or observe live if freshly written
                    cached_dur = self._ag_live_timings.get(step_key)
                    if cached_dur is not None and 500.0 <= cached_dur <= 300000.0:
                        dur_ms = cached_dur
                    elif idx == n - 1:
                        dt = file_mtime - ts
                        if 0.5 <= dt <= 300.0:
                            dur_ms = dt * 1000.0
                            self._ag_live_timings[step_key] = dur_ms
                            self._ag_live_dirty = True

                if dur_ms is not None:
                    timings.append(
                        TimingSample(
                            source="antigravity",
                            model=model_name,
                            timestamp=ts,
                            tokens=out_tok,
                            duration_ms=dur_ms,
                            ttft_ms=None,
                            is_estimated=True,
                        )
                    )

        return events, timings

    def refresh(self):
        # type: () -> None
        """Refresh changed log files incrementally."""
        # 1. Codex files
        codex_paths = set(_discover_codex_files(self.codex_dir))
        for stale in list(self._codex_cache.keys()):
            if stale not in codex_paths:
                del self._codex_cache[stale]

        for path in codex_paths:
            try:
                st = os.stat(path)
                mtime, size = st.st_mtime, st.st_size
            except OSError:
                continue
            cached = self._codex_cache.get(path)
            if cached and cached[0] == mtime and cached[1] == size:
                continue
            events, timings = self._parse_codex_file(path)
            self._codex_cache[path] = (mtime, size, events, timings)

        # 2. Antigravity files
        ag_paths = set(_discover_antigravity_files(self.ag_brain_dir))
        for stale in list(self._ag_cache.keys()):
            if stale not in ag_paths:
                del self._ag_cache[stale]

        for path in ag_paths:
            try:
                st = os.stat(path)
                mtime, size = st.st_mtime, st.st_size
            except OSError:
                continue
            cached = self._ag_cache.get(path)
            if cached and cached[0] == mtime and cached[1] == size:
                continue
            events, timings = self._parse_antigravity_file(path, mtime)
            self._ag_cache[path] = (mtime, size, events, timings)

        self._save_ag_live_timings()
        self.last_refresh_ts = time.time()

    def get_summary(self, source_filter="all", time_range="all"):
        # type: (str, str) -> SummaryStats
        """Aggregate cached records according to source and time range filters."""
        cutoff = get_time_cutoff(time_range)
        summary = SummaryStats()
        by_key = {}  # type: Dict[Tuple[str, str], ModelStats]
        seen_codex_resp = set()

        def ensure_model(src, model):
            key = (src, model)
            ms = by_key.get(key)
            if ms is None:
                ms = ModelStats(model=model, sources=[src])
                by_key[key] = ms
            return ms

        # Collect Codex events
        for _path, (_mt, _sz, events, timings) in self._codex_cache.items():
            for resp_id, ev in events:
                if resp_id is not None:
                    if resp_id in seen_codex_resp:
                        continue
                    seen_codex_resp.add(resp_id)
                if cutoff is not None and ev.timestamp < cutoff:
                    continue

                summary.source_totals["codex"] += ev.total_tokens
                summary.source_requests["codex"] += 1

                if source_filter not in ("all", "codex"):
                    continue

                ms = ensure_model("codex", ev.model)
                ms.requests += 1
                ms.uncached_input += ev.uncached_input
                ms.cached_input += ev.cached_input
                ms.cache_write_input += ev.cache_write_input
                ms.output_tokens += ev.output_tokens
                ms.reasoning_tokens += ev.reasoning_tokens
                ms.total_tokens += ev.total_tokens

            if source_filter in ("all", "codex"):
                for tsamp in timings:
                    if cutoff is not None and tsamp.timestamp < cutoff:
                        continue
                    ms = ensure_model("codex", tsamp.model)
                    if tsamp.duration_ms is not None and tsamp.tokens > 0:
                        ms.timed_count += 1
                        ms.timed_tokens += tsamp.tokens
                        ms.timed_duration_ms += tsamp.duration_ms
                    if tsamp.ttft_ms is not None:
                        ms.ttft_count += 1
                        ms.ttft_total_ms += tsamp.ttft_ms

        # Collect Antigravity events
        for _path, (_mt, _sz, events, timings) in self._ag_cache.items():
            for ev in events:
                if cutoff is not None and ev.timestamp < cutoff:
                    continue

                summary.source_totals["antigravity"] += ev.total_tokens
                summary.source_requests["antigravity"] += 1

                if source_filter not in ("all", "antigravity"):
                    continue

                ms = ensure_model("antigravity", ev.model)
                ms.requests += 1
                ms.uncached_input += ev.uncached_input
                ms.cached_input += ev.cached_input
                ms.output_tokens += ev.output_tokens
                ms.total_tokens += ev.total_tokens

            if source_filter in ("all", "antigravity"):
                for tsamp in timings:
                    if cutoff is not None and tsamp.timestamp < cutoff:
                        continue
                    ms = ensure_model("antigravity", tsamp.model)
                    if tsamp.duration_ms is not None and tsamp.tokens > 0:
                        ms.timed_count += 1
                        ms.timed_tokens += tsamp.tokens
                        ms.timed_duration_ms += tsamp.duration_ms
                        ms.speed_is_estimated = True

        # Finalize costs, totals, and percentage shares
        model_list = [m for m in by_key.values() if m.requests > 0 or m.total_tokens > 0]
        for ms in model_list:
            ms.cost_usd = self.pricing.estimate_cost(
                ms.model, ms.uncached_input, ms.cached_input, ms.output_tokens
            )
            summary.total_tokens += ms.total_tokens
            summary.total_requests += ms.requests
            summary.total_cost_usd += ms.cost_usd
            summary.total_uncached_input += ms.uncached_input
            summary.total_cached_input += ms.cached_input
            summary.total_output_tokens += ms.output_tokens

        model_list.sort(key=lambda m: (-m.total_tokens, -m.requests, m.model))
        for ms in model_list:
            if summary.total_tokens > 0:
                ms.share_pct = (float(ms.total_tokens) / float(summary.total_tokens)) * 100.0
            else:
                ms.share_pct = 0.0

        summary.models = model_list
        return summary
