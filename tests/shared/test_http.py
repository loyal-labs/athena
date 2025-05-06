import pytest

from src.shared.http import AsyncHttpClient

HTTP_URL = "https://example.com"
HTTP_METHOD = "GET"
HTTP_RESPONSE_FILE = "tests/shared/fixtures/http_response.html"


@pytest.mark.asyncio
async def test_http():
    http_client = AsyncHttpClient()
    with open(HTTP_RESPONSE_FILE) as f:
        expected_response = f.read()

    response = await http_client.request(
        HTTP_URL,
        method=HTTP_METHOD,
    )

    assert isinstance(response, str)
    assert response == expected_response
