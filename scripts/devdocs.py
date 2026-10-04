#!/usr/bin/env python3
"""Query the Google Developer Knowledge MCP server (official Google docs).

Usage:
  scripts/devdocs.py search "chronicle RuleDeployment enabled field"
  scripts/devdocs.py get documents/cloud.google.com/chronicle/docs/reference/rest/...

API key: $GOOGLE_DEVKNOWLEDGE_API_KEY, else .chris.json mcpServers entry.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

URL = "https://developerknowledge.googleapis.com/mcp"


def _api_key() -> str:
    key = os.environ.get("GOOGLE_DEVKNOWLEDGE_API_KEY")
    if key:
        return key
    cfg = Path(__file__).resolve().parent.parent / ".chris.json"
    data = json.loads(cfg.read_text())
    return data["mcpServers"]["google-developer-knowledge"]["headers"]["X-Goog-Api-Key"]


def call(tool: str, arguments: dict) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "X-Goog-Api-Key": _api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    if "error" in payload:
        raise SystemExit(f"MCP error: {payload['error']}")
    result = payload["result"]
    return result.get("structuredContent") or result


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("search", "get"):
        raise SystemExit(__doc__)
    cmd, arg = sys.argv[1], " ".join(sys.argv[2:])
    if cmd == "search":
        for r in call("search_documents", {"query": arg}).get("results", []):
            print(f"== {r.get('parent')}\n{r.get('content', '')[:1200]}\n")
    else:
        res = call("get_documents", {"names": [arg]})
        for d in res.get("documents", [res]):
            print(d.get("content", json.dumps(d, indent=2)))


if __name__ == "__main__":
    main()
