import re
from collections import Counter

from pydantic import BaseModel, Field

from .base import JobHandler
from .registry import register


class TextPayload(BaseModel):
    text: str = Field(min_length=1)
    top_n: int = Field(default=5, ge=1, le=50)


@register("TEXT_PROCESSING")
class TextProcessingHandler(JobHandler):
    payload_schema = TextPayload

    def execute(self, payload: TextPayload) -> dict:
        text = payload.text
        words = re.findall(r"[\w']+", text.lower())
        return {
            "word_count": len(words),
            "character_count": len(text),
            "character_count_no_spaces": len(re.sub(r"\s", "", text)),
            "line_count": len(text.splitlines()),
            "sentence_count": len([s for s in re.split(r"[.!?]+", text) if s.strip()]),
            "top_words": [{"word": w, "count": c} for w, c in Counter(words).most_common(payload.top_n)],
        }

