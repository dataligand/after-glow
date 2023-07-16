import asyncio
import json


def connected():
    return {"connected": True}


def progress_update(*, tag, sent, total):
    return {"progress_update": {"tag": tag, "sent": sent, "total": total}}


def unknown_file(file):
    return {"unknown_file": file}


def invalid_file_mode(file_mode):
    return {"invalid_file_mode": file_mode}


def listening():
    return {"listening": True}


def connecting():
    return {"connecting": True}


def new_connection():
    return {"new_connection": True}


def request_file(tag):
    return {"request_tag": tag}


def error(error: str, **kwargs):
    return {"error": error, **kwargs}


def timeout(duration):
    return {"timeout": duration}


def files_already_exist(hashes):
    return {"files_already_exist": hashes}


def write_event_log(log, event):
    match event:
        case {"connected": True}:
            log.info("connected", connected=True)
        case {"progress_update": {"tag": tag, "sent": sent, "total": total}} as event:
            percent = 0 if not sent else sent / total
            log.info(
                "{} @ {:03.2%}".format(tag, percent),
                tag=tag,
                sent=sent,
                total=total,
            )
        case {"request_tag": tag}:
            log.info(f"request: {tag}", tag=tag)
        case {"unknown_file": _file} as event:
            log.warn("unknown_file", **event)
        case {"new_connection": True} as event:
            log.info("new_connection", **event)
        case {"invalid_file_mode": file_mode, **rest} as event:
            log.error("invalid_file_mode", file_mode=file_mode, **rest)
        case {"listening": True}:
            log.info("listening", listening=True)
        case {"connecting": True}:
            log.info("connecting", connecting=True)
        case {"error": error, **rest}:
            log.error("", error=error, **rest)
        case {"timeout": duration}:
            log.error("timeout", duration=duration)
        case {"files_already_exist": hashes}:
            log.info("files_already_exist", hashes=hashes)
        case {"terminate": 1}:
            log.error("Failed to copy all files", exit_code=1)
        case {"terminate": 0}:
            log.info("Success!", exit_code=0)


def new_message_handler(log):
    def inner(log):
        writer: asyncio.StreamWriter = None
        drain_callback = None
        writer_messages = []
        log_events = []
        try:
            while True:
                return_drain_callback = False
                message = yield drain_callback
                match message:
                    case {"set_writer": new_writer}:
                        writer = new_writer
                    case {"log": new_log}:
                        log = new_log
                    case {"bind_context": context}:
                        log = log.bind(**context)
                    case {"set_drain_callback": drain_callback}:
                        drain_callback = drain_callback
                    case {"event": new_event} as message:
                        writer_messages.append(message)
                        log_events.append(new_event)
                    case {"command": command} as message:
                        return_drain_callback = True
                        writer_messages.append(message)
                        log_events.append(command)

                if writer and len(writer_messages):
                    context = log._context if log else {}
                    while len(writer_messages):
                        m = writer_messages.pop()
                        writer.write(f"{json.dumps(dict(context=context, **m))}\n")
                    if return_drain_callback:
                        drain_callback = writer.drain()
                if log:
                    while len(log_events):
                        write_event_log(log, log_events.pop())
        except Exception as e:
            print(e)

    message_handler = inner(log)
    message_handler.send(None)
    return message_handler


def write_event(message_handler, event):
    message_handler.send({"event": event})


def send_terminate(message_handler, exit_code):
    return message_handler.send({"command": {"terminate": exit_code}})


def send_terminate_ack(message_handler):
    return message_handler.send({"command": {"terminate_ack": True}})


def set_log(message_handler, log):
    message_handler.send({"log": log})


def set_drain_callback(message_handler, callback):
    message_handler.send({"set_drain_callback": callback})


def bind_context(message_handler, **context):
    message_handler.send({"bind_context": context})


def set_writer(message_handler, writer):
    message_handler.send({"set_writer": writer})


async def new_event_listener(readline, log, command_handler):
    while True:
        match await readline():
            case "":
                return
            case message:
                match json.loads(message):
                    case {"event": event, "context": context}:
                        write_event_log(log.bind(**context), event)
                    case {"command": command, "context": context}:
                        write_event_log(log.bind(**context), command)
                        command_handler(command)
