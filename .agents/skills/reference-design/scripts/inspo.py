#!/usr/bin/env python3
"""Configure or exercise the public Inspo MCP without third-party Python packages."""
import argparse
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://inspomcp.dev/api/mcp?maxTokens=6000"
REQUIRED = {"recommend", "get_screen", "get_design_system", "search_screens"}


class Client:
    def __init__(self):
        self.sequence = 0
        self.protocol = "2025-03-26"
        self.session = None
        result = self.request("initialize", {
            "protocolVersion": self.protocol, "capabilities": {},
            "clientInfo": {"name": "reference-design-check", "version": "1.0.0"}})
        self.protocol = result["protocolVersion"]
        self.request("notifications/initialized", {}, notification=True)

    def request(self, method, params, notification=False):
        self.sequence += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            body["id"] = self.sequence
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": self.protocol}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=45) as response:
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            raw = response.read(20_000_001)
            if len(raw) > 20_000_000:
                raise RuntimeError("MCP response exceeds 20 MB; narrow the query")
            if notification or not raw:
                return {}
            text = raw.decode("utf-8")
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                messages = [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]
                result = next((item for item in messages if item.get("id") == self.sequence), None)
                if result is None:
                    raise RuntimeError("No matching MCP response")
            else:
                result = json.loads(text)
            if "error" in result:
                raise RuntimeError("MCP error: " + str(result["error"]))
            return result["result"]


def setup():
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI is missing; the call/check fallback still works with Python")
    existing = subprocess.run([executable, "mcp", "get", "inspo", "--json"], capture_output=True, text=True)
    if existing.returncode == 0:
        configuration = json.loads(existing.stdout)
        url = configuration.get("transport", {}).get("url")
        if url not in (ENDPOINT, "https://inspomcp.dev/api/mcp"):
            raise RuntimeError("Existing Inspo configuration differs; preserved without modification")
        if configuration.get("enabled") is False:
            raise RuntimeError("Existing Inspo connection is disabled; preserved without modification")
        print("Existing hosted Inspo connection retained.")
        return
    # Only an explicit missing-server response permits adding a new entry.
    if "not found" not in (existing.stderr + existing.stdout).lower() and "no mcp server named" not in (existing.stderr + existing.stdout).lower():
        raise RuntimeError("Could not inspect Codex configuration; no changes made")
    subprocess.run([executable, "mcp", "add", "inspo", "--url", ENDPOINT], check=True)
    print("Configured. Reload the client if needed; run check for live service proof.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "check", "tools", "call"))
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--args-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.action == "setup":
        setup()
        return
    if args.action == "call" and not (args.tool and args.args_file and args.output_dir):
        parser.error("call requires tool, --args-file and --output-dir")
    if args.output_dir and args.output_dir.exists():
        parser.error("output directory already exists; choose a new directory to preserve earlier evidence")
    payload = json.loads(args.args_file.read_text(encoding="utf-8-sig")) if args.args_file else {}
    if not isinstance(payload, dict):
        parser.error("arguments must be a JSON object")
    client = Client()
    if args.action in ("tools", "check"):
        result = client.request("tools/list", {})
        names = {item["name"] for item in result["tools"]}
        if not REQUIRED.issubset(names):
            raise RuntimeError("Required tools missing: " + ", ".join(sorted(REQUIRED - names)))
        print(json.dumps(result if args.action == "tools" else {"ok": True, "endpoint": ENDPOINT, "tools": sorted(names)}, indent=2))
        return
    result = client.request("tools/call", {"name": args.tool, "arguments": payload})
    if result.get("isError"):
        raise RuntimeError("Tool failed: " + json.dumps(result.get("content", [])))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    blocks = []
    images = []
    for i, block in enumerate(result.get("content", [])):
        if block.get("type") == "image":
            suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(block.get("mimeType"))
            if not suffix:
                raise RuntimeError("Unsupported returned image type")
            path = args.output_dir / ("image-" + str(i) + suffix)
            path.write_bytes(base64.b64decode(block["data"], validate=True))
            images.append(str(path))
            blocks.append({"type": "saved_image", "path": path.name, "mimeType": block["mimeType"]})
        else:
            blocks.append(block)
    result["content"] = blocks
    target = args.output_dir / "result.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "tool": args.tool, "result": str(target), "images": images,
                      "note": "Open returned images before claiming visual inspection."}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print("Inspo: " + str(exc), file=sys.stderr)
        sys.exit(1)
