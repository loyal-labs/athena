import markdown
import orjson
import pytest

from src.telegraph.telegraph_utils import convert_html_to_telegraph_format

MARKDOWN_TEST_FILE_ROUTE = "tests/telegraph/fixtures/telegraph_markdown.md"
HTML_TEST_FILE_ROUTE = "tests/telegraph/fixtures/telegraph_html.html"
DICT_TEST_FILE_ROUTE = "tests/telegraph/fixtures/telegraph_dict.json"


class TestTelegraphConversions:
    """Test suite for Telegraph conversion functions."""

    @pytest.mark.parametrize(
        "test_case,input_file,expected_output_file,conversion_type",
        [
            (
                "markdown_to_html",
                MARKDOWN_TEST_FILE_ROUTE,
                HTML_TEST_FILE_ROUTE,
                "text",
            ),
            (
                "html_to_dict",
                HTML_TEST_FILE_ROUTE,
                DICT_TEST_FILE_ROUTE,
                "json",
            ),
        ],
        ids=["markdown→html", "html→dict"],
    )
    def test_telegraph_conversion(
        self,
        test_case: str,
        input_file: str,
        expected_output_file: str,
        conversion_type: str,
    ):
        """Test telegraph conversion functions with different input formats.

        Args:
            test_case: The name of the test case for better error reporting
            input_file: Path to the input file
            expected_output_file: Path to the file containing expected output
            conversion_type: Type of comparison to perform ('text' or 'json')
        """
        with open(input_file, encoding="utf-8") as f:
            input_content = f.read()

        with open(expected_output_file, encoding="utf-8") as f:
            if conversion_type == "json":
                expected_output = orjson.loads(f.read())
            else:
                expected_output = f.read()

        # -- Test Cases --

        # -- 1. Markdown to HTML --
        if test_case == "markdown_to_html":
            assert markdown.markdown(input_content) == expected_output

        # -- 2. HTML to Dictionary --
        elif test_case == "html_to_dict":
            assert convert_html_to_telegraph_format(input_content) == expected_output
