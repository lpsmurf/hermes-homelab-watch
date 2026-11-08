#!/bin/sh
# Unit tests run outside Hermes; the plugin root is a package, so pytest must root in tests/.
set -e
cd "$(dirname "$0")"
exec .venv/bin/python -m pytest -q -c tests/pytest.ini --rootdir tests tests "$@"
