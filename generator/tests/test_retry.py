"""Тесты политики retry: повторные попытки, backoff, исчерпание."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.retry import RetryError, RetryPolicy  # noqa: E402


class TestRetryPolicy(unittest.TestCase):
    def test_success_on_first_attempt(self):
        policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=1.0)
        sleeps: list[float] = []
        policy._sleep = sleeps.append
        self.assertEqual(policy.execute(lambda: 42), 42)
        self.assertEqual(sleeps, [])

    def test_success_after_failures(self):
        attempts = {"n": 0}

        def flaky() -> int:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("boom")
            return 7

        policy = RetryPolicy(max_attempts=5, base_delay=0.0, max_delay=1.0)
        policy._sleep = lambda _delay: None
        self.assertEqual(policy.execute(flaky), 7)
        self.assertEqual(attempts["n"], 3)

    def test_exhaustion_raises_retry_error(self):
        policy = RetryPolicy(max_attempts=2, base_delay=0.0, max_delay=1.0)
        policy._sleep = lambda _delay: None
        with self.assertRaises(RetryError):
            policy.execute(lambda: (_ for _ in ()).throw(ValueError("always")))

    def test_backoff_grows_and_is_capped(self):
        policy = RetryPolicy(
            max_attempts=10,
            base_delay=0.5,
            max_delay=2.0,
            backoff_factor=2.0,
            jitter=0.0,
        )
        delays = [policy._backoff_delay(attempt) for attempt in range(1, 6)]
        self.assertEqual(delays[0], 0.5)
        self.assertEqual(delays[1], 1.0)
        self.assertEqual(delays[2], 2.0)
        self.assertEqual(delays[3], 2.0, "задержка не должна превышать max_delay")


if __name__ == "__main__":
    unittest.main()
