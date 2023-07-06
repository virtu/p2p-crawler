"""This module contains custom function decorators."""

import functools
import logging as log
import time

cumulative_runtime = {}


def timing(func):
    """Decorator to time function calls and track cumulative function runtime."""

    @functools.wraps(func)
    def wrap(*args, **kw):
        time_start = time.time()
        result = func(*args, **kw)
        runtime = (time.time() - time_start) * 1000
        f = func.__name__
        log.debug("execution time of function %s: %.1f ms.", f, runtime)
        cumulative_runtime[f] = cumulative_runtime.get(f, 0) + runtime
        return result

    return wrap


def print_runtime_stats():
    """Output runtime statistics collected via @timing decorator."""
    for func_name, runtime_ms in cumulative_runtime.items():
        log.info(
            "Cumulative runtime of %s: %.1fs (%dms)",
            func_name,
            runtime_ms / 1000,
            runtime_ms,
        )
