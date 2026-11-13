#!/usr/bin/env python3
"""Static checks for Power Automate (Logic Apps) workflow definitions.

Catches the class of bug Flow Checker misses after renames or moves:
  * runAfter pointing at an action that isn't a sibling in the same scope
  * a "has timed out" branch attached to an action that can never time out (e.g. Set variable)
  * body()/outputs()/actions()/result()/items() referencing an action that doesn't exist
  * variables() / Set / Increment / Append on a variable that was never initialized
  * parameters() referencing an environment variable the definition doesn't declare
  * duplicate action names, runAfter cycles, scopes with no entry action

Usage: python3 scripts/validate_definitions.py flows/*/definition.json
"""
import json
import re
import sys
from pathlib import Path

REF = re.compile(r"\b(body|outputs|actions|result|items)\('([^']+)'\)")
VAR = re.compile(r"\bvariables\('([^']+)'\)")
PARAM = re.compile(r"\bparameters\('([^']+)'\)")
VAR_ACTIONS = {"SetVariable", "IncrementVariable", "DecrementVariable",
               "AppendToArrayVariable", "AppendToStringVariable"}
# Actions that complete instantly and can never end in TimedOut.
NEVER_TIMES_OUT = VAR_ACTIONS | {"InitializeVariable", "Compose", "Query", "Select", "Table", "Join",
                                 "ParseJson", "Terminate"}


def containers(actions, path="root"):
    """Yield (path, dict-of-sibling-actions) for every container level."""
    yield path, actions
    for name, a in actions.items():
        if "actions" in a:
            yield from containers(a["actions"], f"{path}/{name}")
        if "else" in a and "actions" in a["else"]:
            yield from containers(a["else"]["actions"], f"{path}/{name}/else")
        for case_name, case in a.get("cases", {}).items():
            yield from containers(case.get("actions", {}), f"{path}/{name}/{case_name}")
        if "default" in a:
            yield from containers(a["default"].get("actions", {}), f"{path}/{name}/default")


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def check(path):
    errors = []
    data = json.loads(Path(path).read_text())
    definition = data["properties"]["definition"]
    actions = definition["actions"]
    declared_params = set(definition.get("parameters", {}))

    all_names, foreach_names, initialized = [], set(), set()
    for cpath, sibs in containers(actions):
        for name, a in sibs.items():
            all_names.append(name)
            if a.get("type") == "Foreach":
                foreach_names.add(name)
            if a.get("type") == "InitializeVariable":
                if cpath != "root":
                    errors.append(f"{name}: InitializeVariable must be at the top level (found in {cpath})")
                for v in a["inputs"]["variables"]:
                    initialized.add(v["name"])

    dupes = {n for n in all_names if all_names.count(n) > 1}
    for d in sorted(dupes):
        errors.append(f"duplicate action name: {d}")
    names = set(all_names)

    for cpath, sibs in containers(actions):
        if sibs and not any(not a.get("runAfter") for a in sibs.values()):
            errors.append(f"{cpath}: no entry action (every action has a runAfter)")
        for name, a in sibs.items():
            for pred, statuses in (a.get("runAfter") or {}).items():
                if pred not in sibs:
                    errors.append(f"{name}: runAfter '{pred}' is not a sibling in {cpath}")
                bad = set(statuses) - {"Succeeded", "Failed", "Skipped", "TimedOut"}
                if bad:
                    errors.append(f"{name}: invalid runAfter status {sorted(bad)}")
                pred_type = sibs.get(pred, {}).get("type")
                if set(statuses) == {"TimedOut"} and pred_type in NEVER_TIMES_OUT:
                    errors.append(f"{name}: runs only when '{pred}' times out, but a {pred_type} action never "
                                  f"times out, so this branch can never run")
        # cycle check (Kahn)
        deps = {n: set((a.get("runAfter") or {}).keys()) & set(sibs) for n, a in sibs.items()}
        ready = [n for n, d in deps.items() if not d]
        seen = 0
        while ready:
            n = ready.pop()
            seen += 1
            for m, d in deps.items():
                if n in d:
                    d.discard(n)
                    if not d:
                        ready.append(m)
        if seen != len(sibs):
            errors.append(f"{cpath}: runAfter cycle detected")

    def walk(actions_dict):
        for name, a in actions_dict.items():
            yield name, a
            if "actions" in a:
                yield from walk(a["actions"])
            if "else" in a:
                yield from walk(a["else"].get("actions", {}))
            for case in a.get("cases", {}).values():
                yield from walk(case.get("actions", {}))
            if "default" in a:
                yield from walk(a["default"].get("actions", {}))

    for name, a in walk(actions):
        own = {k: v for k, v in a.items() if k not in ("actions", "else", "cases", "default")}
        for s in strings(own):
            for kind, ref in REF.findall(s):
                if kind == "items" and ref not in foreach_names:
                    errors.append(f"{name}: items('{ref}') does not name a Foreach")
                elif ref not in names:
                    errors.append(f"{name}: {kind}('{ref}') references a missing action")
            for v in VAR.findall(s):
                if v not in initialized:
                    errors.append(f"{name}: variables('{v}') is never initialized")
            for p in PARAM.findall(s):
                if p not in declared_params:
                    errors.append(f"{name}: parameters('{p}') is not declared")
        if a.get("type") in VAR_ACTIONS and a["inputs"]["name"] not in initialized:
            errors.append(f"{name}: {a['type']} on uninitialized variable '{a['inputs']['name']}'")

    for tname, t in definition["triggers"].items():
        for s in strings(t):
            for p in PARAM.findall(s):
                if p not in declared_params:
                    errors.append(f"trigger {tname}: parameters('{p}') is not declared")

    return len(all_names), errors


def main(paths):
    failed = False
    for p in paths:
        try:
            count, errors = check(p)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"FAIL {p}: {e}")
            failed = True
            continue
        status = "ok  " if not errors else "FAIL"
        print(f"{status} {p} ({count} actions)")
        for e in errors:
            print(f"     - {e}")
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or sorted(str(p) for p in Path("flows").glob("*/definition.json"))))
