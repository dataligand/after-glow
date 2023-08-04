import pytest
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def root_key_pair():
    return tuple([f"{CURRENT_DIR}/{file}" for file in ("root_key", "root_key.pub")])


@pytest.fixture
def other_key_pair():
    return tuple([f"{CURRENT_DIR}/{file}" for file in ("other_key", "other_key.pub")])
