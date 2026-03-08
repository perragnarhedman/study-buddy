from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Placeholder auth helper for the separate Classroom test generator."
    )
    parser.add_argument(
        "--env-path",
        default="test generator/.env.local",
        help="Path to the generator env file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_path)
    print("Generator auth helper is not enabled yet.")
    print(f"Expected config path: {env_path}")
    print("Next auth milestone:")
    print("- verify OAuth scopes in Google Cloud Data Access")
    print("- verify app audience/testing state")
    print("- verify the teacher account is an allowed test user")
    print("- save tokens only under test generator/tokens/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
