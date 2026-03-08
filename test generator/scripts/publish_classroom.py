from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Placeholder publisher for the Classroom test generator."
    )
    parser.add_argument("--input", required=True, help="Approved draft JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Live Classroom publishing is not enabled in markdown-first mode.")
    print(f"Approved draft path: {args.input}")
    print("Use the markdown outputs for review until the separate OAuth path is stable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
