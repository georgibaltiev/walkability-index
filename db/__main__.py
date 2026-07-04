
import argparse
import sys

from db.connection import engine
from db.pipeline import STEPS, STEP_MAP


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m db")
    parser.add_argument(
        "step",
        nargs="?",
        choices=[name for name, _ in STEPS] + ["all"],
        help="Pipeline step to run. Use 'all' to run them in order.",
    )
    parser.add_argument("--list", action="store_true",
                        help="List available steps in execution order.")
    args = parser.parse_args(argv)

    if args.list:
        for name, _ in STEPS:
            print(name)
        return 0

    if args.step is None:
        parser.print_help()
        return 1

    eng = engine()
    if args.step == "all":
        for name, runner in STEPS:
            print(f"\n=== Step: {name} ===")
            runner(eng)
    else:
        STEP_MAP[args.step](eng)
    return 0


if __name__ == "__main__":
    sys.exit(main())
