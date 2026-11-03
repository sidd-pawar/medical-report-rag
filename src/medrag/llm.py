"""
llm.py - the shared code for calling an LLM with a schema and caching its answer.

Several parts of the project ask an LLM to read a document and reply in a fixed
shape (lab reports, prescriptions, ...). They all need the same two things, so they
live here once instead of being copied into each file:

    make_openai_parser()  Creates a function that sends text to OpenAI and returns a
                          Pydantic object, using "structured outputs".
    cached_parse()        Checks the cache first; only calls the LLM if this document
                          hasn't been processed before, then saves the answer.

A "parser" here is any function:  text -> (Pydantic object, token usage)
Tests pass in fake parsers, so they never call OpenAI.
"""

import json
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel

from .config import CHAT_MODEL, get_api_key

# TypeVar lets the type hints say "whatever schema you pass in is what you get back".
# e.g. cached_parse(..., schema=ExtractedReport) returns an ExtractedReport.
Schema = TypeVar("Schema", bound=BaseModel)

Parser = Callable[[str], tuple[BaseModel, dict]]


def make_openai_parser(schema: type[Schema], instructions: str, model: str = CHAT_MODEL) -> Parser:
    """
    Create a function that asks OpenAI to read some text and reply in `schema`'s shape.

    Args:
        schema:       The Pydantic class the reply must fit, e.g. ExtractedReport.
        instructions: The system prompt explaining the task.
        model:        Which OpenAI model to use (default from .env).

    Returns:
        A function: text -> (schema object, {"input_tokens": .., "output_tokens": ..})
    """
    from openai import OpenAI   # imported here so tests don't need OpenAI set up

    client = OpenAI(api_key=get_api_key())

    def parse(text: str) -> tuple[Schema, dict]:
        response = client.responses.parse(
            model=model,
            instructions=instructions,   # the "system" instructions
            input=text,                  # the document text
            text_format=schema,          # the schema the reply must follow
            temperature=0,               # least random: same input -> (nearly) same output
            # (If you switch to a "reasoning" model such as o-series, remove temperature:
            #  those models don't accept it.)
        )
        usage = {"input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}
        return response.output_parsed, usage

    return parse


def cached_parse(doc_id: str, text: str, cache_dir: Path, schema: type[Schema],
                 make_parser: Callable[[], Parser], model: str = CHAT_MODEL) -> Schema:
    """
    Get the LLM's structured answer for one document, using the cache if possible.

    Args:
        doc_id:      Used as the cache file name, e.g. "P001-RX-2023-07-25".
        text:        The document text to send if it isn't cached.
        cache_dir:   Folder holding one JSON file per document.
        schema:      The Pydantic class of the answer (used to check cached answers).
        make_parser: A function that creates the parser. It's only called if the
                     answer isn't cached, so a cached run never needs an API key.
        model:       Model name, recorded in the cache file for reference.

    Returns:
        The answer, as an instance of `schema`.
    """
    cache_file = cache_dir / f"{doc_id}.json"
    if cache_file.exists():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        # model_validate checks the saved JSON still fits the schema
        return schema.model_validate(saved["report"])

    answer, usage = make_parser()(text)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "doc_id": doc_id,
        "model": model,
        "usage": usage,
        "report": answer.model_dump(),   # model_dump turns the object into a plain dict
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return answer