"""Pool lifetime, thread isolation, and seeded application results."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
import unittest
from unittest.mock import MagicMock, patch

from dnd5ecombat.process_execution import process_map, process_worker_limit, with_process_pools
from dnd5ecombat.gui_service import SimulationSettings, run_simulations
from dnd5ecombat.profile_catalog import discover_characters, discover_monsters


class ProcessExecutionTests(unittest.TestCase):
    def test_nested_runs_reuse_capacity_and_close_pool(self):
        @with_process_pools
        def nested():
            return process_map(abs, (-1, -2, -3), 4)

        @with_process_pools
        def run():
            process_map(abs, (-1, -2), 4)
            nested()

        with patch("dnd5ecombat.process_execution.ProcessPoolExecutor") as pool:
            pool.return_value.map.side_effect = lambda f, jobs: map(f, jobs)
            run()
            pool.assert_called_once_with(max_workers=4)
            self.assertEqual(pool.return_value.map.call_count, 2)
            pool.return_value.shutdown.assert_called_once_with(wait=True, cancel_futures=True)
            run()
            self.assertEqual(pool.call_count, 2)

    def test_failure_closes_pool_and_resets_scope(self):
        @with_process_pools
        def run():
            process_map(abs, (-1, -2), 2)

        with patch("dnd5ecombat.process_execution.ProcessPoolExecutor") as pool:
            pool.return_value.map.side_effect = RuntimeError("failed worker")
            with self.assertRaisesRegex(RuntimeError, "failed worker"):
                run()
            pool.return_value.shutdown.assert_called_once()
            pool.return_value.map.side_effect = lambda f, jobs: map(f, jobs)
            run()
            self.assertEqual(pool.call_count, 2)

    def test_serial_empty_and_single_jobs_do_not_start_processes(self):
        @with_process_pools
        def run():
            self.assertEqual(process_map(abs, (), 10), ())
            self.assertEqual(process_map(abs, (-3,), 10), (3,))
            self.assertEqual(process_map(abs, (-3, -4), 1), (3, 4))

        with patch("dnd5ecombat.process_execution.ProcessPoolExecutor") as pool:
            run()
            pool.assert_not_called()

    def test_concurrent_runs_have_separate_pool_lifetimes(self):
        barrier = Barrier(2)

        @with_process_pools
        def run():
            process_map(abs, (-1, -2), 2)
            barrier.wait(timeout=5)
            return process_map(abs, (-3, -4), 2)

        def executor(**kwargs):
            instance = MagicMock()
            instance.map.side_effect = lambda f, jobs: map(f, jobs)
            return instance

        with patch("dnd5ecombat.process_execution.ProcessPoolExecutor", side_effect=executor) as pool:
            with ThreadPoolExecutor(max_workers=2) as threads:
                futures = [threads.submit(run) for _ in range(2)]
                self.assertEqual([future.result() for future in futures], [(3, 4), (3, 4)])
            self.assertEqual(pool.call_count, 2)

    def test_windows_worker_limit(self):
        with patch("dnd5ecombat.process_execution.sys.platform", "win32"):
            self.assertEqual(process_worker_limit(128), 61)
            self.assertEqual(process_worker_limit(10), 10)
        with patch("dnd5ecombat.process_execution.sys.platform", "linux"):
            self.assertEqual(process_worker_limit(128), 128)

    def test_single_profile_shared_pool_matches_serial_all_tabs(self):
        build = discover_characters()[0].value
        monster = next(item.value for item in discover_monsters() if item.value.name == "Goblin")
        settings = SimulationSettings(trials=5, seed=43)
        serial = run_simulations(build, monster, settings)
        parallel = run_simulations(build, monster, replace(settings, workers=3))
        for section in ("attacks", "turns", "saving_throws", "duels"):
            expected, actual = getattr(serial, section), getattr(parallel, section)
            self.assertEqual(actual.rows, expected.rows)
            self.assertEqual(actual.note, expected.note)
            self.assertEqual(actual.metadata["settings"]["workers"], 3)
