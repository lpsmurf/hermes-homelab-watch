"""Import the plugin directory as package ``homelab_watch`` (its folder name is not importable)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("homelab_watch", ROOT / "__init__.py",
                                              submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
sys.modules["homelab_watch"] = module
spec.loader.exec_module(module)
