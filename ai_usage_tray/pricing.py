# -*- coding: utf-8 -*-
"""Model pricing table (USD per 1M tokens) with persistent user overrides."""

import json
import os
from typing import Dict, Tuple

from .platform_utils import get_config_dir

CONFIG_DIR = get_config_dir()
PRICING_FILE = os.path.join(CONFIG_DIR, "pricing.json")

# Pricing in USD per 1,000,000 tokens:
#   input: uncached input tokens
#   cached_input: cache-read input tokens
#   output: output tokens (including reasoning)
DEFAULT_PRICING = {
    # Gemini / Antigravity models
    "gemini-4-neon": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
    "gemini-4-neon-high": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
    "gemini-4-neon-low": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gemini-3-pro": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
    "gemini-3-flash": {"input": 0.50, "cached_input": 0.05, "output": 3.00},
    "gemini-2.5-pro": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "cached_input": 0.03, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "cached_input": 0.01, "output": 0.40},

    # OpenAI / Codex models
    "gpt-6.2-astra": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-6.2-sol": {"input": 5.00, "cached_input": 0.50, "output": 20.00},
    "codex-auto-review": {"input": 0.50, "cached_input": 0.05, "output": 2.00},
    "gpt-5": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-codex": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-4.1": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "o3": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "o4-mini": {"input": 1.10, "cached_input": 0.275, "output": 4.40},

    # Claude models (in case used inside Antigravity)
    "claude-sonnet-4": {"input": 3.00, "cached_input": 0.30, "output": 15.00},
    "claude-opus-4": {"input": 15.00, "cached_input": 1.50, "output": 75.00},
    "claude-3-7-sonnet": {"input": 3.00, "cached_input": 0.30, "output": 15.00},
    "claude-3-5-sonnet": {"input": 3.00, "cached_input": 0.30, "output": 15.00},

    # Fallback default
    "_default": {"input": 2.00, "cached_input": 0.20, "output": 10.00},
}


class PricingManager(object):
    """Loads, matches, edits, and saves per-model token pricing."""

    def __init__(self, pricing_path=PRICING_FILE):
        # type: (str) -> None
        self.pricing_path = pricing_path
        self.prices = {}  # type: Dict[str, Dict[str, float]]
        self.reload()

    def reload(self):
        # type: () -> None
        merged = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
        if os.path.isfile(self.pricing_path):
            try:
                with open(self.pricing_path, "r", encoding="utf-8") as fh:
                    user_data = json.load(fh)
                if isinstance(user_data, dict):
                    for k, v in user_data.items():
                        if isinstance(v, dict):
                            merged[str(k)] = {
                                "input": float(v.get("input", 2.0)),
                                "cached_input": float(v.get("cached_input", 0.2)),
                                "output": float(v.get("output", 10.0)),
                            }
            except Exception:
                pass
        self.prices = merged

    def save(self, custom_prices=None):
        # type: (Dict[str, Dict[str, float]]) -> None
        if custom_prices is not None:
            self.prices = custom_prices
        os.makedirs(os.path.dirname(self.pricing_path), exist_ok=True)
        with open(self.pricing_path, "w", encoding="utf-8") as fh:
            json.dump(self.prices, fh, indent=2, ensure_ascii=False, sort_keys=True)

    def get_rate(self, model_name):
        # type: (str) -> Tuple[float, float, float]
        """Return (input, cached_input, output) USD per 1M tokens."""
        name = (model_name or "").strip().lower()
        if name in self.prices:
            r = self.prices[name]
            return r["input"], r["cached_input"], r["output"]

        # Longest prefix / substring match
        best_key = None
        best_len = 0
        for key in self.prices:
            if key == "_default":
                continue
            kl = key.lower()
            if name.startswith(kl) or kl in name:
                if len(kl) > best_len:
                    best_len = len(kl)
                    best_key = key

        if best_key is not None:
            r = self.prices[best_key]
            return r["input"], r["cached_input"], r["output"]

        # Family heuristics
        if "flash-lite" in name:
            r = self.prices.get("gemini-2.5-flash-lite", self.prices["_default"])
        elif "flash" in name or "mini" in name or "review" in name:
            r = self.prices.get("gemini-3-flash", self.prices["_default"])
        elif "opus" in name:
            r = self.prices.get("claude-opus-4", self.prices["_default"])
        elif "claude" in name or "sonnet" in name:
            r = self.prices.get("claude-sonnet-4", self.prices["_default"])
        else:
            r = self.prices["_default"]
        return r["input"], r["cached_input"], r["output"]

    def estimate_cost(self, model_name, uncached_input, cached_input, output_tokens):
        # type: (str, int, int, int) -> float
        in_rate, cache_rate, out_rate = self.get_rate(model_name)
        cost = (
            (max(0, int(uncached_input)) * in_rate)
            + (max(0, int(cached_input)) * cache_rate)
            + (max(0, int(output_tokens)) * out_rate)
        ) / 1000000.0
        return cost
