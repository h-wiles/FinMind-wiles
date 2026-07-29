"""Entry point: python -m report_search

Starts the MCP server over stdio so DeerFlow's Gateway can discover
and invoke its tools.
"""

import asyncio
import logging
import sys

from report_search.server import run_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,  # stdio MCP — keep stdout clean for JSON-RPC
)

logger = logging.getLogger("report_search")


def main() -> None:
    """Run the stdio MCP server."""
    logger.info("Starting report-search MCP server")
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
