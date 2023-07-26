import argparse

from . import child, parent


def new():
    parser = argparse.ArgumentParser(
        description="Copy files from one machine to another"
    )

    sub_parsers = parser.add_subparsers(required=True, metavar="[parent | child]")

    child_parser = sub_parsers.add_parser("child", help="copy files onto this machine")
    child.arguments(child_parser)
    child_parser.set_defaults(module=child)

    parent_parser = sub_parsers.add_parser(
        "parent", help="copy files from this machine"
    )
    parent.arguments(parent_parser)
    parent_parser.set_defaults(module=parent)

    return parser
