def as_bytes(s):
    return bytes(s, "utf-8")


def as_utf8(b: bytes):
    return b.decode("utf-8")


def parse_files(files):
    return {tag: path for [tag, path] in (tag_file.split(":") for tag_file in files)}
