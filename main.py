"""Application entry point for the PACT formatter."""

import runpy
import sys
from pathlib import Path


def main():
    if "--cli" in sys.argv[1:]:
        cli_path = Path(__file__).resolve().parent / "interfaces" / "cli.py"
        runpy.run_path(str(cli_path), run_name="__main__")
        return 0

    from interfaces.gui import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
