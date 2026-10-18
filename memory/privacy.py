import copy
import os.path
import tempfile
from datetime import datetime, timezone

import yaml

import init
import threading

PRIVACY_LOCK = threading.RLock()


def resolve_mode_rules(modes):
    """Resolve inherited rules without modifying the original YAML data."""
    resolved = {}

    def normalize_rule(rule):
        rule = copy.deepcopy(rule)
        providers = rule.get("providers", [])

        if isinstance(providers, str):
            providers = [
                p.strip() for p in providers.split(",") if p.strip()
            ]
        elif not isinstance(providers, list):
            raise ValueError("Rule providers must be a string or list")

        rule["providers"] = providers
        return rule

    def resolve(mode, stack=None):
        stack = set() if stack is None else stack

        if mode in resolved:
            return copy.deepcopy(resolved[mode])

        if mode in stack:
            raise ValueError(f"Cyclic mode inheritance: {mode}")

        if mode not in modes:
            raise ValueError(f"Unknown inherited mode: {mode}")

        stack.add(mode)
        definition = modes[mode]
        rules = []

        parent = definition.get("extends")
        if parent:
            rules.extend(resolve(parent, stack))

        rules.extend(
            normalize_rule(rule)
            for rule in definition.get("hide", [])
        )

        stack.remove(mode)
        resolved[mode] = rules
        return copy.deepcopy(rules)

    for mode in modes:
        resolve(mode)

    return resolved


def get_all_privacy_rules() -> dict:
    modes = load_privacy_config()
    return resolve_mode_rules(modes['modes'])


def get_current_privacy_rules():
    curr = get_all_privacy_rules()
    return curr[init.MODE]


def load_privacy_config():
    with open(os.path.join(init.DATA_DIR, "privacy.yaml")) as f:
        return yaml.safe_load(f)


def save_privacy_config(config):
    """Write atomically so a failed write won't leave a partial YAML file."""
    # directory = os.path.dirname(PRIVACY_FILE)PRIVACY_FILE

    fd, temp_path = tempfile.mkstemp(
        dir=init.DATA_DIR,
        prefix=".privacy-",
        suffix=".yaml",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                config,
                f,
                sort_keys=False,
                allow_unicode=True,
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, os.path.join(init.DATA_DIR, "privacy.yaml"))

    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def validate_rules(rules):
    if not isinstance(rules, list):
        raise ValueError("'hide' must be a list")

    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Each rule must be an object")

        providers = rule.get("providers")
        if isinstance(providers, str):
            providers = [
                p.strip() for p in providers.split(",") if p.strip()
            ]
        elif isinstance(providers, list):
            if not all(isinstance(p, str) and p.strip() for p in providers):
                raise ValueError("Providers must be non-empty strings")
            providers = [p.strip() for p in providers]
        else:
            raise ValueError("'providers' must be a string or list")

        if not providers:
            raise ValueError("Select at least one provider")

        rule["providers"] = providers
        parsed_dates = {}

        for field in ("from", "to"):
            value = rule.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"'{field}' is required")

            try:
                parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC")
                parsed = parsed.replace(tzinfo=timezone.utc)
                parsed_dates[field] = parsed
                rule[field] = parsed.strftime("%Y-%m-%d %H:%M:%S UTC")

            except ValueError:
                raise ValueError(
                    f"'{field}' must use YYYY-MM-DD HH:MM:SS UTC"
                )

        start = parsed_dates["from"]
        end = parsed_dates["to"]

        if start >= end:
            raise ValueError("'from' must be earlier than 'to'")

    return rules
