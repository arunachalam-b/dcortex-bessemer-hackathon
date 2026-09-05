import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crew_ops import load_world  # noqa: E402


@pytest.fixture(scope="session")
def world():
    return load_world()


@pytest.fixture(scope="session")
def dataset(world):
    def load(name):
        with open(os.path.join(world.data_dir, name)) as fh:
            return json.load(fh)
    return load
