import json
from abc import ABC, abstractmethod

from pydantic import BaseModel, ValidationError

from ..domain import InvalidPayload


class JobHandler(ABC):
    payload_schema: type[BaseModel]

    def validate_payload(self, payload: dict) -> BaseModel:
        try:
            return self.payload_schema.model_validate(payload)
        except ValidationError as exc:
            raise InvalidPayload(json.loads(exc.json(include_url=False, include_input=False))) from exc

    def handle(self, payload: dict) -> dict:
        return self.execute(self.validate_payload(payload))

    @abstractmethod
    def execute(self, payload: BaseModel) -> dict: ...
