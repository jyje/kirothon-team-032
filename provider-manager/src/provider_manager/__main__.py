"""CLI: `python -m provider_manager status` or `... ask [--provider NAME] "prompt"`."""

from __future__ import annotations

import sys

from provider_manager.config import codex_enabled
from provider_manager.factory import PROVIDERS, ask, describe, is_configured, resolve

USAGE = 'usage: python -m provider_manager status | ask [--provider NAME] "prompt"'


def main(argv: list[str]) -> int:
    cmd, rest = (argv[0] if argv else "status"), argv[1:]
    if cmd == "status":
        for name in PROVIDERS:
            off = name == "codex" and not codex_enabled()
            mark = "off " if off else "ok  " if is_configured(name) else "--  "
            print(mark + describe(name))
        print(f"active: {resolve()}")
        return 0
    provider = None
    if rest[:1] == ["--provider"] and len(rest) > 1:
        provider, rest = rest[1], rest[2:]
    if cmd == "ask" and rest:
        try:
            print(ask(" ".join(rest), provider))
        except (ValueError, RuntimeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
