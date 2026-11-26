"""Library tests never touch the network: link metadata comes from `fake_fetcher`."""

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI

from app.modules.library.metadata import Metadata, get_metadata_fetcher


@dataclass
class FakeFetcher:
    """Returns `result` (None means the fetch failed) and records each (url, kind)."""

    result: Metadata | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def __call__(self, url: str, kind: str) -> Metadata | None:
        self.calls.append((url, kind))
        return self.result


@pytest.fixture(autouse=True)
def fake_fetcher(app: FastAPI) -> FakeFetcher:
    fake = FakeFetcher()
    app.dependency_overrides[get_metadata_fetcher] = lambda: fake
    return fake
