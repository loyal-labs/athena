import json

import pytest
from pydantic import HttpUrl

from src.telegraph.telegraph_service import TelegraphService

PATH_TO_FIXTURES = "tests/telegraph/fixtures"


@pytest.fixture
def telegraph_service():
    return TelegraphService()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_case,expected_fixture",
    [
        ("api", "get_page_api_response.json"),
    ],
)
async def test_telegraph_service(
    test_case: str,
    expected_fixture: str,
    telegraph_service: TelegraphService,
):
    page = await telegraph_service.get_page(test_case)
    page_json = page.model_dump()

    with open(f"{PATH_TO_FIXTURES}/{expected_fixture}") as f:
        expected_page_json = json.load(f)

    entries_to_check = ["path", "url", "title", "description", "image_url", "content"]
    for entry in entries_to_check:
        if isinstance(page_json[entry], HttpUrl):
            page_json[entry] = str(page_json[entry])
        assert page_json[entry] == expected_page_json[entry]
