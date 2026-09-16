"""Rotate a bounded portal-secret batch; repeat with the returned last_id."""

import argparse
import json

from app.services.secrets import rotate_portal_secrets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--after-id", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(rotate_portal_secrets(args.batch_size, args.after_id), sort_keys=True))


if __name__ == "__main__":
    main()
