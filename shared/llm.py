"""One function to ask an LLM for structured output. The provider is chosen in config.py.

To add a provider: write a function with the same signature and register it in PROVIDERS.
"""

from typing import TypeVar

import anthropic
import openai
from pydantic import BaseModel

from shared import cache
from shared.settings import config

Schema = TypeVar("Schema", bound=BaseModel)


def ask(prompt: str, schema: type[Schema]) -> Schema:
    """Send the prompt to the configured LLM and return its answer as a `schema` instance."""
    model = config.LLM_MODELS[config.LLM_PROVIDER]

    def fetch() -> dict:
        answer = PROVIDERS[config.LLM_PROVIDER](prompt, schema, model)
        if answer is None:
            raise RuntimeError(f"{config.LLM_PROVIDER} ({model}) returned no structured answer")
        return answer.model_dump()

    key = {"llm": config.LLM_PROVIDER, "model": model, "schema": schema.__name__, "prompt": prompt}
    return schema.model_validate(cache.get_or_fetch(key, fetch))


def _ask_openai(prompt: str, schema: type[Schema], model: str) -> Schema | None:
    response = openai.OpenAI().responses.parse(model=model, input=prompt, text_format=schema)
    return response.output_parsed


def _ask_anthropic(prompt: str, schema: type[Schema], model: str) -> Schema | None:
    response = anthropic.Anthropic().messages.parse(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    return response.parsed_output


PROVIDERS = {
    "openai": _ask_openai,
    "anthropic": _ask_anthropic,
}
