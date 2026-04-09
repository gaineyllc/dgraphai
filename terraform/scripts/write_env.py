#!/usr/bin/env python3
"""
Read terraform output JSON and write to .env.test file.

Usage:
  cd terraform/environments/dev
  terraform output -json | python3 ../../scripts/write_env.py > ../../../.env.test
"""
import json, sys

data = json.load(sys.stdin)
for key, val in data.items():
    if isinstance(val.get("value"), str):
        # Multi-line env block
        for line in val["value"].strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                print(line)
