"""Start the field client server from anywhere: ``python serve_field.py``.

Same as ``python -m pedsim serve`` run inside ``python/``, without depending on
the working directory. ``PORT`` in the environment picks the port.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pedsim.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["serve", *sys.argv[1:]]))
