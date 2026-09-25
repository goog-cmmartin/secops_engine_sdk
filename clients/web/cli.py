#!/usr/bin/env python3
"""CLI Launcher for the SecOps Multi-Agent Fleet Web Chat Interface."""

import argparse
import sys
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the SecOps Multi-Agent Fleet Web Chat UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print("=" * 70)
    print(" Google SecOps Multi-Agent Fleet & Actions Proposal Engine")
    print("=" * 70)
    print(f" Web UI running at: http://{args.host}:{args.port}")
    print(" Zulip-inspired Stream & Topic collaboration active.")
    print(" Human-In-The-Loop review cards ready for live mutation approval.")
    print("=" * 70)

    try:
        uvicorn.run(
            "clients.web.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\nSecOps Chat Server stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
