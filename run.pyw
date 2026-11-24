#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windowless Windows entrypoint (runs with pythonw.exe without console window)."""

import sys

from ai_usage_tray.app import main

if __name__ == "__main__":
    sys.exit(main())
