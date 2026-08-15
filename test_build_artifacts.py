#!/usr/bin/env python
"""Test script to verify build_artifacts tool works."""

import sys
import json
from mcp_server.server import build_artifacts

if __name__ == "__main__":
    league = sys.argv[1] if len(sys.argv) > 1 else "wnba"
    result = build_artifacts(league)
    print(json.dumps(result, indent=2))
