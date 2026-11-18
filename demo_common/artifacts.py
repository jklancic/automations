"""Readable events and per-run artifacts, not an orchestration abstraction."""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO


class Story:
    def __init__(self, output_root: Path, stream: TextIO | None = None, *, prefix: str = "run-"):
        output_root.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix=prefix, dir=output_root))
        self.trace_path = self.directory / "trace.jsonl"
        self.trace_path.touch(exist_ok=False)
        self.stream = stream if stream is not None else sys.stdout
        self.sequence = 0
        self.secrets = [key for key in [os.environ.get("AI_PROXY_API_KEY", "")] if key]

    def safe(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in value)
        if isinstance(value, dict):
            return {self.safe(key): self.safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.safe(item) for item in value]
        return value

    def event(self, owner: str, stage: str, message: str, **details):
        self.sequence += 1
        event = self.safe({
            "sequence": self.sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "owner": owner,
            "stage": stage,
            "message": message,
            "details": details,
        })
        # Append only: earlier events are never rewritten during the run.
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"[{owner}] {stage}: {event['message']}", file=self.stream, flush=True)

    def result(self, result: dict):
        result = self.safe(result)
        with (self.directory / "result.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"[RESULT] Artifacts saved under {self.safe(str(self.directory))}", file=self.stream, flush=True)
        return result
