import stat
import os


def check_permission(file_path: str):
    file_stat = os.stat(file_path)
    uid = os.getuid()

    if not uid == file_stat.st_uid:
        raise PermissionError(
            f"Current user {uid} cannot read {file_path} owned by {file_stat.st_uid}"
        )

    st_mode = file_stat.st_mode
    if stat.S_IRWXG & st_mode or stat.S_IRWXO & st_mode:
        raise PermissionError("Public key file permissions are too permissive")

    if not stat.S_IRUSR & st_mode:
        raise PermissionError(f"Owner can not read {file_path}")
