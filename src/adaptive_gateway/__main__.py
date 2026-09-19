"""CLI entrypoint: `python -m adaptive_gateway [--port ...] [--config ...]`."""
from __future__ import annotations

import argparse
import os

from adaptive_gateway.config import load_config
from adaptive_gateway.server import serve
from adaptive_gateway.version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="adaptive-gateway",
                                     description="Adaptive LLM inference gateway")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--config", default=os.environ.get("GATEWAY_CONFIG", None))
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return
    config = load_config(args.config)
    serve(args.host, args.port, config)


if __name__ == "__main__":
    main()
