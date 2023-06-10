import asyncio, asyncssh, argparse
from functools import partial
from pathlib import Path
import message
import structlog
from datetime import datetime, timedelta
import traceback
from pathlib import Path
from files import parse_files, as_utf8, as_bytes


def arguments(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--private-key", type=str, required=True, help="Path to private key file"
    )

    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="The port on which the server will listen",
    )

    parser.add_argument(
        "--files", nargs="+", required=True, help="Colon seperated file:path mapping"
    )

    parser.add_argument(
        "--timeout",
        default=300,
        help="The time window for which files are expeted to be copied across",
    )


async def copy_files(conn, tagged_files, message_handler, callback):
    file_metadata = {}
    exit_code = 0

    def progress_handler(tag, _dest, sent, total):
        nonlocal file_metadata
        try:
            current_time = datetime.utcnow()

            if (current_time - file_metadata[tag]) > timedelta(
                seconds=2
            ) or sent == total:
                message.write_event(
                    message_handler,
                    message.progress_update(tag=as_utf8(tag), sent=sent, total=total),
                )
                file_metadata[tag] = current_time

        except Exception as e:
            message.write_event(
                message_handler, message.error(str(e), tb=traceback.format_exc())
            )

    def error_handler(e):
        nonlocal exit_code
        exit_code = 1
        message.write_event(message_handler, message.error(str(e)))

    try:
        jobs = [
            (
                tag,
                asyncssh.scp(
                    (conn, tag),
                    path,
                    progress_handler=progress_handler,
                    error_handler=error_handler,
                ),
            )
            for (tag, path) in tagged_files.items()
        ]

        for tag, job in jobs:
            file_metadata[as_bytes(tag)] = datetime.utcnow()
            message.write_event(message_handler, message.request_file(tag))
            await job

    except Exception as e:
        message.write_event(
            message_handler, message.error(str(e), tb=traceback.format_exc())
        )
    finally:
        callback(exit_code)


def validate_paths(paths) -> int:
    return all(map(lambda path: Path(path).exists(), paths))


def command_handler(
    callback,
    command,
):
    match command:
        case {"terminate_ack": exit_code}:
            callback(exit_code)


async def listen(*, port, private_key, tagged_files, log, loop) -> int:
    timeout_duration = 300
    exit_code = 1
    ssh_acceptor = None
    terminate_ack = loop.create_future()
    finished_scp = loop.create_future()

    message_handler = message.new_message_handler(
        log.bind(client=True, port=port, file_tags=list(tagged_files.keys()))
    )

    message.write_event(message_handler, message.listening())

    async def handle_connection(conn: asyncssh.SSHClientConnection) -> None:
        try:
            process = await conn.create_process()
            message.set_writer(message_handler, process.stdin)
            await asyncio.gather(
                copy_files(
                    conn,
                    tagged_files,
                    message_handler,
                    callback=finished_scp.set_result,
                ),
                message.new_event_listener(
                    process.stdout.readline,
                    log,
                    partial(command_handler, terminate_ack.set_result),
                ),
            )
        except Exception as e:
            message.write_event(
                message_handler, message.error(str(e), tb=traceback.format_exc())
            )

    try:
        async with asyncio.timeout(timeout_duration):
            ssh_acceptor = await asyncssh.listen_reverse(
                port=port,
                known_hosts=None,
                client_keys=private_key,
                acceptor=handle_connection,
                reuse_address=True,
            )

            while exit_code > 0:
                exit_code = await finished_scp

                exit_code = exit_code or int(not validate_paths(tagged_files.values()))

                await message.send_terminate(message_handler, exit_code)

                try:
                    async with asyncio.timeout(10):
                        await terminate_ack
                except Exception:
                    pass

                if exit_code > 0:
                    terminate_ack = loop.create_future()
                    finished_scp = loop.create_future()

    except asyncio.TimeoutError:
        message.write_event(message_handler, message.timeout(timeout_duration))

    except Exception as e:
        message.write_event(
            message_handler, message.error(str(e), tb=traceback.format_exc())
        )
    finally:
        if ssh_acceptor:
            ssh_acceptor.close()
        return exit_code


async def main(args, loop):
    exit_code = 1
    try:
        log = structlog.get_logger(__name__)

        port, private_key, tagged_files = (
            args.port,
            args.private_key,
            parse_files(args.files),
        )

        paths = list(tagged_files.values())
        if validate_paths(paths):
            message.write_event_log(log, message.files_already_exist(paths))
            return 0

        for _tag, path in tagged_files.items():
            Path(path).mkdir(parents=True, exist_ok=True)

        exit_code = await listen(
            port=port,
            private_key=private_key,
            tagged_files=tagged_files,
            log=log,
            loop=loop,
        )

    except Exception as e:
        message.write_event_log(log, message.error(str(e)), tb=traceback.format_exc())
    finally:
        return exit_code
