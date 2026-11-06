from ..domain import UnknownJobType
from .base import JobHandler


class HandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str):
        def decorator(handler_cls: type[JobHandler]):
            if job_type in self._handlers:
                raise ValueError(f"Handler for {job_type!r} already registered")
            self._handlers[job_type] = handler_cls()
            return handler_cls

        return decorator

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError:
            raise UnknownJobType(f"Unsupported job type: {job_type}") from None

    def types(self) -> list[str]:
        return sorted(self._handlers)


registry = HandlerRegistry()
register = registry.register
