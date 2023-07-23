from datetime import datetime, timedelta
from functools import partial
import hashlib
import os
from pathlib import Path
import shutil
import structlog
from tempfile import mkstemp
import traceback

import asyncio, asyncssh, argparse

from . import message
from .files import parse_files, as_utf8, as_bytes


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
        "--lock-path",
        default="./afterglow.lock",
        type=str,
        help="Path to write the lockfile to",
    )

    parser.add_argument(
        "--timeout",
        default=300,
        help="The time window for which files are expeted to be copied across",
    )


async def scp_copy(
    conn,
    file_tag: str,
    dest: str,
    progress_handler,
    error_handler,
    message_handler,
    set_error,
    file_hashes: dict,
):
    try:
        (tempfd, temp_path) = mkstemp()
        await asyncssh.scp(
            (conn, file_tag),
            temp_path,
            progress_handler=progress_handler,
            error_handler=error_handler,
        )
    except Exception as e:
        os.close(tempfd)
        set_error()
        message.write_event(
            message_handler, message.error(str(e), tb=traceback.format_exc())
        )

    else:
        os.close(tempfd)

        with open(temp_path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256")

        try:
            shutil.move(temp_path, dest)
        except Exception as e:
            set_error()
            message.write_event(
                message_handler, message.error(str(e), tb=traceback.format_exc())
            )
            os.remove(temp_path)
        else:
            file_hashes[file_tag] = digest.hexdigest()


async def copy_files(conn, tagged_files, message_handler, callback):
    file_metadata = {}
    exit_code = 0
    file_hashes = {}

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

    def set_error():
        nonlocal exit_code
        exit_code = 1

    try:
        jobs = [
            (
                tag,
                scp_copy(
                    conn=conn,
                    file_tag=tag,
                    dest=path,
                    progress_handler=progress_handler,
                    error_handler=error_handler,
                    message_handler=message_handler,
                    set_error=set_error,
                    file_hashes=file_hashes,
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
        callback((exit_code, file_hashes))


def validate_paths(paths) -> int:
    return all(map(lambda path: Path(path).exists(), paths))


def command_handler(
    callback,
    command,
):
    match command:
        case {"terminate_ack": exit_code}:
            callback(exit_code)


async def listen(*, port, private_key, tagged_files, lock_path, log, loop) -> int:
    timeout_duration = 300
    exit_code = 1
    ssh_acceptor = None
    file_hashes = {}
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
                exit_code, file_hashes = await finished_scp

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

        if exit_code == 0:
            path = Path(lock_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "w") as f:
                f.write(
                    "\n".join(
                        [
                            f"{file_tag} = {sha256}"
                            for file_tag, sha256 in file_hashes.items()
                        ]
                    )
                )

        return exit_code


async def main(args, loop):
    exit_code = 1
    try:
        log = structlog.get_logger(__name__)

        port, private_key, tagged_files, lock_path = (
            args.port,
            args.private_key,
            parse_files(args.files),
            args.lock_path,
        )

        try:
            with open(lock_path, "r") as f:
                message.write_event_log(
                    log, message.files_already_exist(hashes=list(f.readlines()))
                )
            return 0
        except OSError:
            pass

        for _tag, path in tagged_files.items():
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        exit_code = await listen(
            port=port,
            private_key=private_key,
            tagged_files=tagged_files,
            lock_path=lock_path,
            log=log,
            loop=loop,
        )

    except Exception as e:
        message.write_event_log(log, message.error(str(e), tb=traceback.format_exc()))
    else:
        return exit_code
