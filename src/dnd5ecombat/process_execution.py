"""Reuse lazy process pools within one application run, isolated by context."""

from concurrent.futures import ProcessPoolExecutor
from contextvars import ContextVar
from functools import wraps
import sys


_run_pools = ContextVar("simulation_run_pools", default=None)


def process_worker_limit(workers):
    # Windows ProcessPoolExecutor cannot wait on more than 61 workers.
    return min(workers, 61) if sys.platform == "win32" else workers


def with_process_pools(function):
    """Own pools for the outermost call and close them even after a failure.

    Context variables keep concurrent GUI threads/runs separate. Pools are
    created only when a batch actually has multiple independent jobs.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _run_pools.get() is not None:
            return function(*args, **kwargs)
        pools = {}
        token = _run_pools.set(pools)
        try:
            return function(*args, **kwargs)
        finally:
            _run_pools.reset(token)
            for executor in pools.values():
                executor.shutdown(wait=True, cancel_futures=True)
    return wrapped


def process_map(function, jobs, workers):
    jobs = tuple(jobs)
    if workers == 1 or len(jobs) <= 1:
        return tuple(function(job) for job in jobs)
    pools = _run_pools.get()
    workers = process_worker_limit(workers)
    if pools is None:
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
            return tuple(executor.map(function, jobs))
    if workers not in pools:
        # Keep capacity for later, larger batches instead of sizing to the first.
        pools[workers] = ProcessPoolExecutor(max_workers=workers)
    return tuple(pools[workers].map(function, jobs))
