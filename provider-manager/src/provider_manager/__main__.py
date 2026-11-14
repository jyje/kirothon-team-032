"""CLI: `python -m provider_manager status` or `... ask "prompt"`."""

from __future__ import annotations

import sys

from provider_manager.registry import PROVIDERS, get_provider


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        for cls in PROVIDERS.values():
            p = cls()
            print(("ok  " if p.is_configured() else "--  ") + p.describe())
        return 0
    if cmd == "ask" and len(argv) > 1:
        print(get_provider().complete(" ".join(argv[1:])))
        return 0
    print('usage: python -m provider_manager status | ask "prompt"', file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
