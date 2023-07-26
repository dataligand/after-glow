import asyncio
import structlog
import sys

from . import argparser, message


async def main(args, log):
    exit_code = 1
    try:
        async with asyncio.timeout(args.timeout):
            exit_code = await args.module.main(args, loop)
    except Exception as e:
        message.write_event_log(log, message.error(str(e)))
    finally:
        sys.exit(exit_code)


loop = asyncio.get_event_loop()

log = structlog.getLogger(__name__)

loop.run_until_complete(main(argparser.new().parse_args(), log))
