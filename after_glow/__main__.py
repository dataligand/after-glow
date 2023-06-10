import argparse
import asyncio
import structlog
import parent
import child
import message
import sys

parser = argparse.ArgumentParser(description="Copy files from one machine to another")

sub_parsers = parser.add_subparsers(required=True, metavar="[parent | child]")

child_parser = sub_parsers.add_parser("child", help="copy files onto this machine")
child.arguments(child_parser)
child_parser.set_defaults(module=child)


parent_parser = sub_parsers.add_parser("parent", help="copy files from this machine")
parent.arguments(parent_parser)
parent_parser.set_defaults(module=parent)


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

loop.run_until_complete(main(parser.parse_args(), log))
