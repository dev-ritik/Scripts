from datetime import datetime, date, time

import yaml

import init

PRIVACY_RULES = {}


def resolve_mode_rules(modes: dict) -> dict:
    resolved = {}

    for mode_params in modes.values():
        for rule in mode_params.get("hide", []):
            rule["providers"] = rule.get("providers", "").split(",")

    def resolve(mode: str, stack=None):
        if stack is None:
            stack = set()

        if mode in resolved:
            return resolved[mode]

        if mode in stack:
            raise ValueError(f"Cyclic mode inheritance: {mode}")

        stack.add(mode)

        mode_def = modes.get(mode, {})
        rules = []

        parent = mode_def.get("extends")
        if parent:
            # TODO: Deep copy
            rules.extend(resolve(parent, stack))

        rules.extend(mode_def.get("hide", []))

        resolved[mode] = rules
        stack.remove(mode)
        return rules

    for mode in modes:
        resolve(mode)

    return resolved


def load_visibility():
    global PRIVACY_RULES
    if not PRIVACY_RULES:
        with open('data/privacy.yaml') as f:
            modes = yaml.safe_load(f)
            PRIVACY_RULES = resolve_mode_rules(modes['modes'])
    return PRIVACY_RULES[init.MODE]


def is_hidden(message: 'Message') -> bool:
    rules = load_visibility()
    for rule in rules:
        if rule["providers"] != 'all' and message.provider not in rule["providers"]:
            continue

        start = rule["from"]
        if isinstance(start, date):
            start = datetime.combine(start, time(0, 0, 0))
        end = rule["to"]
        if isinstance(end, date):
            end = datetime.combine(end, time(23, 59, 59))

        if start <= message.datetime <= end:
            return True

    return False
