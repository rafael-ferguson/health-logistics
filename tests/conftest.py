from pathlib import Path

import pytest

from lab import enable_logging

TEST_DIR: Path = Path(__file__).resolve().parent
TMP_DIR: Path = TEST_DIR / "tmp"
FILE_DIR: Path = TEST_DIR / "files"


def pytest_sessionstart(session):
    r"""Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    TMP_DIR.mkdir(exist_ok=True)


@pytest.fixture
def test_dir() -> Path:
    return TEST_DIR


@pytest.fixture
def tmp_dir() -> Path:
    return TMP_DIR


@pytest.fixture
def file_dir() -> Path:
    return FILE_DIR


@pytest.fixture(scope="session", autouse=True)
def turn_on_logging() -> None:
    enable_logging(10)
