"""Entry point for the alerts cron job. Hermes runs the generated script in HERMES_HOME/scripts/ with its own
Python, outside the plugin loader (so it works under plugin host isolation too); the script calls main().

Prints only incidents that opened or resolved since the last tick, so an unchanged homelab is a silent run.
A broken targets file exits non-zero, which Hermes delivers as a failure notice instead of staying quiet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PACKAGE = "homelab_watch"


def _load_package(plugin_dir: Path):
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    spec = importlib.util.spec_from_file_location(PACKAGE, plugin_dir / "__init__.py",
                                                  submodule_search_locations=[str(plugin_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


def main(plugin_dir: str, targets_path: str, state_path: str) -> int:
    _load_package(Path(plugin_dir))
    from homelab_watch.report import alert_text
    from homelab_watch.service import Watch
    from homelab_watch.targets import TargetsError

    try:
        rnd, targets = Watch(Path(targets_path), Path(state_path)).check()
    except TargetsError as exc:
        print(f"Homelab Watch cannot run: {exc}", file=sys.stderr)
        return 2
    text = alert_text(rnd, targets)
    if text:
        print(text)
    return 0
