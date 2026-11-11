"""Download every source into a new snapshot folder data/raw/<YYYY-MM-DD>/.

Each snapshot is frozen: evals and indexes point at one snapshot, so a new run
never overwrites an old one (it refuses if today's folder already exists).

Run: uv run python -m wizzair_rag.download
"""

import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from wizzair_rag.sources import SOURCES, Source

RAW_DIR = Path("data/raw")
# wizzair.com serves the same SSR page to a plain browser user agent; no JS needed.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"


def fetch(source: Source) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    data = None
    if source.post_json is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(source.post_json).encode()
    request = urllib.request.Request(source.url, data=data, headers=headers)  # data set -> POST
    with urllib.request.urlopen(request, timeout=60) as response:
        # urllib follows redirects silently; a moved page would be saved under the wrong id.
        if response.geturl() != source.url:
            raise RuntimeError(f"{source.url} redirected to {response.geturl()}, update sources.py")
        return response.read()


def main() -> None:
    snapshot_dir = RAW_DIR / datetime.now(timezone.utc).date().isoformat()
    snapshot_dir.mkdir(parents=True)  # raises FileExistsError: today's snapshot is already taken
    manifest = {}
    for source in SOURCES:
        body = fetch(source)
        file = snapshot_dir / f"{source.id}.{source.kind}"
        file.write_bytes(body)
        manifest[source.id] = {
            "url": source.url,
            "file": file.name,
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }
        print(f"{source.id}: {len(body):,} bytes")
        time.sleep(1)  # be polite to wizzair.com
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
