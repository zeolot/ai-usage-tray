# -*- coding: utf-8 -*-
"""Unit tests for cross-platform paths, log parsing, pricing, and UI rendering."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ai_usage_tray.collector import UsageCollector, parse_iso_timestamp
from ai_usage_tray import platform_utils
from ai_usage_tray.pricing import PricingManager


class TestCrossPlatformUsageTray(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai_usage_tray_test_")
        self.codex_dir = os.path.join(self.tmp, "codex", "sessions", "2026", "11", "24")
        self.ag_dir = os.path.join(
            self.tmp, "ag", "brain", "conv-001", ".system_generated", "logs"
        )
        os.makedirs(self.codex_dir, exist_ok=True)
        os.makedirs(self.ag_dir, exist_ok=True)

        # Write sample Codex JSONL (including duplicate response_id to verify dedup)
        codex_lines = [
            {
                "timestamp": "2026-11-24T06:00:00.000Z",
                "type": "turn_context",
                "payload": {"turn_id": "t1", "model": "gpt-6.2-astra"},
            },
            {
                "timestamp": "2026-11-24T06:00:05.000Z",
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t1",
                    "response_id": "resp-1",
                    "usage": {
                        "input_tokens": 10000,
                        "cached_input_tokens": 8000,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 500,
                        "reasoning_output_tokens": 100,
                        "total_tokens": 10500,
                    },
                },
            },
            # Duplicate response_id should be ignored
            {
                "timestamp": "2026-11-24T06:00:05.100Z",
                "type": "token_usage_record",
                "payload": {
                    "turn_id": "t1",
                    "response_id": "resp-1",
                    "usage": {
                        "input_tokens": 10000,
                        "cached_input_tokens": 8000,
                        "output_tokens": 500,
                        "total_tokens": 10500,
                    },
                },
            },
            {
                "timestamp": "2026-11-24T06:00:06.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "turn_id": "t1",
                    "item": {"type": "AgentMessage"},
                    "content_token_count": 200,
                    "started_at_ms": 10000,
                    "completed_at_ms": 14000,
                },
            },
            {
                "timestamp": "2026-11-24T06:00:06.100Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "t1",
                    "duration_ms": 6000,
                    "time_to_first_token_ms": 2500,
                },
            },
        ]
        with open(os.path.join(self.codex_dir, "rollout-1.jsonl"), "w", encoding="utf-8") as fh:
            for item in codex_lines:
                fh.write(json.dumps(item) + "\n")

        # Write sample Antigravity transcript.jsonl
        ag_lines = [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "created_at": "2026-11-24T06:10:00Z",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-24T06:10:00Z",
                "model": "gemini-4-neon-high",
                "input_tokens": 2000,
                "cache_read_tokens": 18000,
                "output_tokens": 600,
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "GENERIC",
                "created_at": "2026-11-24T06:10:06Z",
            },
        ]
        with open(os.path.join(self.ag_dir, "transcript.jsonl"), "w", encoding="utf-8") as fh:
            for item in ag_lines:
                fh.write(json.dumps(item) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_iso_timestamp_parser(self):
        t1 = parse_iso_timestamp("2026-11-24T06:00:00Z")
        t2 = parse_iso_timestamp("2026-11-24T06:00:00.500Z")
        t3 = parse_iso_timestamp("2026-11-24T14:00:00+08:00")
        self.assertIsNotNone(t1)
        self.assertAlmostEqual(t2 - t1, 0.5, places=3)
        self.assertAlmostEqual(t1, t3, places=3)

    def test_collector_codex_and_antigravity_metrics(self):
        pricing = PricingManager(os.path.join(self.tmp, "pricing.json"))
        col = UsageCollector(
            pricing_manager=pricing,
            codex_dir=os.path.join(self.tmp, "codex", "sessions"),
            ag_brain_dir=os.path.join(self.tmp, "ag", "brain"),
        )
        col.refresh()
        summary = col.get_summary("all", "all")
        self.assertEqual(summary.total_requests, 2)
        self.assertEqual(summary.total_tokens, 10500 + 20600)

        by_model = {m.model: m for m in summary.models}
        cx = by_model["gpt-6.2-astra"]
        self.assertEqual(cx.requests, 1)
        self.assertEqual(cx.uncached_input, 2000)
        self.assertEqual(cx.cached_input, 8000)
        self.assertAlmostEqual(cx.cache_hit_pct, 80.0, places=2)
        self.assertAlmostEqual(cx.tokens_per_sec, 50.0, places=2)
        self.assertAlmostEqual(cx.avg_ttft_sec, 2.5, places=2)
        self.assertFalse(cx.speed_is_estimated)

        ag = by_model["gemini-4-neon-high"]
        self.assertEqual(ag.requests, 1)
        self.assertEqual(ag.uncached_input, 2000)
        self.assertEqual(ag.cached_input, 18000)
        self.assertEqual(ag.total_tokens, 20600)
        self.assertAlmostEqual(ag.cache_hit_pct, 90.0, places=2)
        self.assertAlmostEqual(ag.tokens_per_sec, 100.0, places=2)
        self.assertTrue(ag.speed_is_estimated)
        self.assertIsNone(ag.avg_ttft_sec)

    def test_windows_env_paths(self):
        with mock.patch.object(platform_utils, "IS_WINDOWS", True), mock.patch.dict(
            os.environ,
            {
                "APPDATA": "/fake/AppData/Roaming",
                "LOCALAPPDATA": "/fake/AppData/Local",
                "CODEX_HOME": "/fake/custom-codex",
                "ANTIGRAVITY_HOME": "/fake/custom-ag",
            },
            clear=False,
        ):
            self.assertTrue(platform_utils.get_config_dir().endswith("ai-usage-tray"))
            self.assertIn("Roaming", platform_utils.get_config_dir())
            self.assertIn("Local", platform_utils.get_cache_dir())
            self.assertTrue(platform_utils.get_codex_sessions_dir().endswith("sessions"))
            self.assertTrue(platform_utils.get_antigravity_brain_dir().endswith("brain"))


if __name__ == "__main__":
    unittest.main()
