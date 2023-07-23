from functools import partial
import traceback

import asyncssh, argparse
from asyncssh.misc import MaybeAwait
import structlog


from . import message
from .files import parse_files, as_utf8, as_bytes


def arguments(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--private-key", type=str, required=True, help="Path to private key file"
    )

    parser.add_argument(
        "--child-key",
        type=str,
        required=True,
        help="Path to childs public key",
    )

    parser.add_argument(
        "--ip", type=str, required=True, help="The ip addres to connect to"
    )

    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="The port to connect to",
    )

    parser.add_argument(
        "--files", nargs="+", required=True, help="Colon seperated file:path mapping"
    )

    parser.add_argument(
        "--timeout",
        default=300,
        help="The time window for which files are expeted to be copied across",
    )


def command_handler(
    callback,
    command,
):
    match command:
        case {"terminate": exit_code}:
            callback(exit_code)


async def bootstrap_child(
    *, ip, port, private_key, child_key, tagged_files, log, loop
) -> int:
    terminate = loop.create_future()

    message_handler = message.new_message_handler(
        log.bind(server=True, ip=ip, port=port)
    )
    message.write_event(message_handler, message.connecting())

    async def process_factory(process: asyncssh.SSHServerProcess) -> None:
        try:
            message.set_writer(message_handler, process.stdout)
            message.write_event(message_handler, message.connected())
            await message.new_event_listener(
                process.stdin.readline,
                log,
                partial(command_handler, terminate.set_result),
            )
        except Exception as e:
            message.write_event(
                message_handler, message.error(str(e), tb=traceback.format_exc())
            )
            raise e

    class FileMap(asyncssh.SFTPServer):
        def map_path(self, tag: bytes) -> bytes:
            try:
                return super().map_path(as_bytes(tagged_files[as_utf8(tag)]))
            except KeyError:
                message.write_event(message_handler, message.unknown_file(as_utf8(tag)))
                return b""

        async def open(
            self, path: bytes, pflags: int, attrs: asyncssh.SFTPAttrs
        ) -> MaybeAwait[object]:
            if not (pflags & asyncssh.constants.FXF_READ):
                # Only allow files to be read (for copying)
                # no writing or modifying the current file
                message.write_event(message_handler, message.invalid_file_mode(pflags))
                raise FileNotFoundError

            try:
                return super().open(path, pflags, attrs)
            except Exception as e:
                message.write_event(
                    message_handler,
                    message.error(str(e), tb=traceback.format_exc()),
                )

    conn = await asyncssh.connect_reverse(
        ip,
        port,
        server_host_keys=private_key,
        authorized_client_keys=child_key,
        process_factory=process_factory,
        sftp_factory=FileMap,
        allow_scp=True,
    )

    result = await terminate

    await message.send_terminate_ack(message_handler)
    conn.close()

    return result


async def main(args, loop):
    exit_code = 1
    try:
        log = structlog.get_logger(__name__)

        (
            ip,
            port,
            private_key,
            child_key,
            tagged_files,
        ) = (
            args.ip,
            args.port,
            args.private_key,
            args.child_key,
            parse_files(args.files),
        )

        exit_code = await bootstrap_child(
            ip=ip,
            port=port,
            private_key=private_key,
            child_key=child_key,
            tagged_files=tagged_files,
            log=log,
            loop=loop,
        )
    except Exception as e:
        message.write_event_log(log, message.error(str(e)), tb=traceback.format_exc())
    finally:
        return exit_code
