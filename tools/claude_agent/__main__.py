import asyncio
import sys

from tools.claude_agent.cli import main


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
