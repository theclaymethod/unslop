#!/usr/bin/env python3
"""Wikipedia fetches must reject off-site responses and oversized bodies."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import wiki_sync  # noqa: E402


class _Body:
    def __init__(self, data: bytes, url: str) -> None:
        self._data = data
        self._url = url

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0 or n >= len(self._data):
            chunk, self._data = self._data, b""
            return chunk
        chunk, self._data = self._data[:n], self._data[n:]
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _page(content: str) -> bytes:
    return json.dumps(
        {
            "query": {
                "pages": [
                    {
                        "revisions": [
                            {
                                "revid": 5,
                                "timestamp": "2026-01-01T00:00:00Z",
                                "slots": {"main": {"content": content}},
                            }
                        ]
                    }
                ]
            }
        }
    ).encode("utf-8")


def main() -> int:
    original = wiki_sync.urllib.request.urlopen
    happy = redirect = size = "skipped"

    def use(body: _Body):
        def _open(*_args: object, **_kwargs: object) -> _Body:
            return body

        wiki_sync.urllib.request.urlopen = _open

    try:
        use(_Body(_page("== Hi ==\nhello"), "https://en.wikipedia.org/w/api.php?titles=x"))
        rev_id, _timestamp, content = wiki_sync.fetch_latest_revision()
        happy = "ok" if rev_id == 5 and "hello" in content else "bad"

        use(
            _Body(
                _page("stolen"),
                "http://169.254.169.254/latest/meta-data",
            )
        )
        try:
            wiki_sync.fetch_latest_revision()
            redirect = "followed"
        except wiki_sync.urllib.error.URLError:
            redirect = "refused"
        except Exception as exc:  # noqa: BLE001
            redirect = type(exc).__name__

        use(
            _Body(
                b"x" * 3_000_000,
                "https://en.wikipedia.org/w/api.php?titles=x",
            )
        )
        try:
            wiki_sync.fetch_latest_revision()
            size = "accepted"
        except ValueError as exc:
            size = "capped" if "size" in str(exc).lower() else "other"
        except Exception as exc:  # noqa: BLE001
            size = type(exc).__name__
    finally:
        wiki_sync.urllib.request.urlopen = original

    print(f"wiki-fetch happy={happy} redirect={redirect} size={size}")
    return 0 if (happy, redirect, size) == ("ok", "refused", "capped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
