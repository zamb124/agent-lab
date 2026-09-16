"""Эталон code_agent CLI: interrupt artifact в JSON-ответе."""

from __future__ import annotations

import json
import sys


def main() -> None:
    extra = " ".join(sys.argv[1:])
    payload = {
        "text": extra,
        "interrupt": {
            "kind": "user_message",
            "question": extra if extra else "need input",
        },
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
