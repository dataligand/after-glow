import pytest
import subprocess
from afterglow.files import as_utf8


@pytest.mark.parametrize(
    "command",
    [
        (
            "python -m afterglow parent --files na:./na "
            "--private-key {private} --child-key {pub} "
            "--ip localhost --port 8022"
        ),
        (
            "python -m afterglow child --files na:/.na "
            "--private-key {private} --port 8022"
        ),
    ],
)
def test_private_key_permission_errors(command, root_key_pair, other_key_pair):
    for private, pub in (root_key_pair, other_key_pair):
        result = subprocess.run(
            command.format(private=private, pub=pub).split(),
            capture_output=True,
        )

        assert result.returncode == 1

        assert "PermissionError" in as_utf8(result.stdout)
