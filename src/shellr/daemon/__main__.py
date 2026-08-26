"""Run shellrd as ``python -m shellr.daemon``.

Equivalent to the ``shellrd`` console script installed by pip.
"""

from shellr.daemon import main

if __name__ == "__main__":
    raise SystemExit(main())
