#!/usr/bin/env python3
"""Validate every schema-bearing file in the repo. Exit 0 = ALL SCHEMAS OK."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:  # noqa: BLE001
        errors.append(f"{path}: invalid JSON: {e}")
        return None


def req(obj, path, keys):
    for k in keys:
        if not isinstance(obj, dict) or k not in obj:
            errors.append(f"{path}: missing required key '{k}'")


# tasks.json registry
tasks = load_json(ROOT / "benchmarks" / "fam-r" / "tasks.json")
if tasks is not None:
    req(tasks, "tasks.json", ["family", "tasks"])
    seen = set()
    for t in tasks.get("tasks", []):
        req(t, f"tasks.json:{t.get('id')}", ["id", "kind", "title"])
        if t.get("id") in seen:
            errors.append(f"tasks.json: duplicate id {t.get('id')}")
        seen.add(t.get("id"))
        d = ROOT / "benchmarks" / "fam-r" / "tasks" / t.get("id", "")
        for fn in ("prompt.md", "check.sh", "EVAL.json"):
            if not (d / fn).exists():
                errors.append(f"tasks/{t.get('id')}: missing {fn}")
        gate = load_json(d / "EVAL.json") if (d / "EVAL.json").exists() else None
        if gate is not None:
            req(gate, f"tasks/{t.get('id')}/EVAL.json",
                ["task_id", "family", "pass_threshold", "verdict_map", "cost_numeraire"])
            if gate.get("task_id") != t.get("id"):
                errors.append(f"tasks/{t.get('id')}/EVAL.json: task_id mismatch")

# capability registry schema must itself be valid + well-formed
schema = load_json(ROOT / "prototype" / "capability-registry.schema.json")
if schema is not None:
    req(schema, "capability-registry.schema.json", ["title", "properties"])

# live registry, if present, must satisfy the schema's required entry keys
live = ROOT / "prototype" / "capability-registry.json"
if live.exists():
    reg = load_json(live)
    if reg is not None and schema is not None:
        req(reg, "capability-registry.json", ["registry_version", "capabilities"])
        entry_keys = schema["properties"]["capabilities"]["items"]["required"]
        for c in reg.get("capabilities", []):
            req(c, f"registry:{c.get('id')}", entry_keys)
            if c.get("status") == "promoted" and len(c.get("admitted_after", [])) != 2:
                errors.append(f"registry:{c.get('id')}: promoted without 2-ship admission")

if errors:
    print("SCHEMA ERRORS:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("ALL SCHEMAS OK")
