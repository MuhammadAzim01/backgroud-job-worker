import random
from dataclasses import dataclass
from typing import Callable

from ..domain import PermanentJobError


@dataclass(frozen=True)
class RetryPolicy:
    base_delay: float = 5.0
    factor: float = 5.0
    max_delay: float = 125.0
    jitter: float = 0.2
    rng: Callable[[], float] = random.random

    def next_delay(self, attempts_made: int) -> float:
        raw = min(self.base_delay * self.factor ** max(attempts_made - 1, 0), self.max_delay)
        return raw * (1 + self.jitter * self.rng())

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        return not isinstance(exc, PermanentJobError)
