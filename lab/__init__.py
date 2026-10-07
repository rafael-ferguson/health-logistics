"""
# lab: Core Utilities and Shared Research Tools

This package serves as the centralized library for your computational
research project. It provides a shared set of high-performance
tools, data structures, and utility functions to ensure reproducibility
and efficiency across different student projects.

## Usage

Instead of rewriting common functions, you should contribute to and
import from this package. For example:

```python
from lab import hpc

hpc.submit_slurm_job(script="docking.py", nodes=1, mem="16G")
```

## Contribution Guidelines

All new classes and functions must include Google-style docstrings.
If you find yourself copying code between two different files, it belongs here in `lab`.
"""

import os
import sys
from ast import literal_eval
from typing import Any

from loguru import logger

logger.disable(name="lab")

LOG_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def enable_logging(
    level_set: int,
    stdout_set: bool = True,
    file_path: str | None = None,
    log_format: str = LOG_FORMAT,
) -> None:
    r"""Enable logging.

    Args:
        level: Requested log level: `10` is debug, `20` is info.
        file_path: Also write logs to files here.
    """
    config: dict[str, Any] = {"handlers": []}
    if stdout_set:
        config["handlers"].append(
            {
                "sink": sys.stdout,
                "level": level_set,
                "format": log_format,
                "colorize": True,
            }
        )
    if isinstance(file_path, str):
        config["handlers"].append(
            {
                "sink": file_path,
                "level": level_set,
                "format": log_format,
                "colorize": False,
            }
        )
    # https://loguru.readthedocs.io/en/stable/api/logger.html#loguru._logger.Logger.configure
    logger.configure(**config)

    logger.enable("lab")


if literal_eval(os.environ.get("LAB_LOG", "False")):
    level = int(os.environ.get("LAB_LOG_LEVEL", 20))
    stdout = literal_eval(os.environ.get("LAB_STDOUT", "True"))
    log_file_path = os.environ.get("LAB_LOG_FILE_PATH", None)
    enable_logging(level, stdout, log_file_path)
