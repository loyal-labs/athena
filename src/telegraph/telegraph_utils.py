"""
Inspired, cleaned up and adapted from converter.py from html_telegraph_poster (https://github.com/mercuree/html-telegraph-poster)
Copyright (c) 2016 Garry G
Licensed under the MIT License
"""

import json
import re
from typing import Any, cast
from urllib.parse import quote_plus, urlparse

from lxml import html
from lxml.html.clean import Cleaner

from src.telegraph.telegraph_constants import (
    ALLOWED_TAGS,
    ALLOWED_TOP_LEVEL_TAGS,
    ELEMENTS_WITH_TEXT,
    HEADER_RE,
    LINE_BREAKS_AND_EMPTY_STRINGS,
    LINE_BREAKS_INSIDE_PRE,
    PRE_CONTENT_RE,
    TELEGRAM_EMBED_IFRAME_RE,
    TELEGRAM_EMBED_SCRIPT_RE,
    TWITTER_RE,
    VIMEO_RE,
    YOUTUBE_RE,
)
from src.telegraph.telegraph_exceptions import InvalidHTML
from src.telegraph.telegraph_schemas import OutputFormat


def clean_article_html(html_string: str) -> str:
    """
    Cleans an HTML string to prepare it for Telegraph conversion.

    This involves:
    - Normalizing header tags (h1->h3, h2/h5/h6->h4).
    - Replacing <b> with <strong>.
    - Converting Telegram embed scripts to iframes.
    - Removing <head> sections.
    - Using lxml.html.clean.Cleaner to remove unwanted tags and attributes.
    - Removing line breaks and empty strings (except inside <pre> tags).
    - Replacing <br> tags with newline characters.

    Args:
        html_string: The raw HTML string to clean.

    Returns:
        The cleaned HTML string, stripped of leading/trailing whitespace.
    """
    html_string = html_string.replace("<h1", "<h3").replace("</h1>", "</h3>")
    # telegram will convert <b> anyway
    html_string = re.sub(r"<(/?)b(?=\s|>)", r"<\1strong", html_string)
    html_string = re.sub(r"<(/?)(h2|h5|h6)", r"<\1h4", html_string)
    # convert telegram embed posts before cleaner
    html_string = re.sub(
        TELEGRAM_EMBED_SCRIPT_RE,
        r'<iframe src="https://t.me/\1"></iframe>',
        html_string,
    )
    # remove <head> if present (can't do this with Cleaner)
    html_string = HEADER_RE.sub("", html_string)

    c = Cleaner(
        allow_tags=ALLOWED_TAGS,
        style=True,
        remove_unknown_tags=False,
        embedded=False,
        safe_attrs_only=True,
        safe_attrs=("src", "href", "class"),
    )

    html_string = f"<div>{html_string}</div>"
    cleaned = c.clean_html(html_string)
    # remove wrapped div
    cleaned = cleaned[5:-6]
    # remove all line breaks and empty strings
    html_string = replace_line_breaks_except_pre(cleaned)
    # replace br with a line break
    html_string = re.sub(r"(<br(/?>|\s[^<>]*>)\s*)+", "\n", html_string)

    return html_string.strip(" \t")


def replace_line_breaks_except_pre(html_string: str, replace_by: str = " ") -> str:
    """
    Replaces line breaks and non-breaking spaces in an HTML string, preserving those within <pre> tags.

    Identifies <pre> tag content and replaces line breaks (\n, \r) and non-breaking spaces (\u00a0)
    with the specified replacement string (defaulting to a space) in the parts of the string
    *outside* the <pre> tags. Inside <pre> tags, line breaks are normalized to '\n'.

    Args:
        html_string: The HTML string to process.
        replace_by: The string to replace line breaks and non-breaking spaces with
                      outside of <pre> tags. Defaults to " ".

    Returns:
        The processed HTML string with line breaks handled differently inside and
        outside of <pre> tags.
    """

    pre_ranges = [0]
    out = ""

    # replace non-breaking space with usual space
    html_string = html_string.replace("\u00a0", " ")

    # get <pre> start/end postion
    for x in PRE_CONTENT_RE.finditer(html_string):
        start, end = x.start(), x.end()
        pre_ranges.extend((start, end))
    pre_ranges.append(len(html_string))

    # all odd elements are <pre>, leave them untouched
    for k in range(1, len(pre_ranges)):
        part = html_string[pre_ranges[k - 1] : pre_ranges[k]]
        if k % 2 == 0:
            out += LINE_BREAKS_INSIDE_PRE.sub("\n", part)
        else:
            out += LINE_BREAKS_AND_EMPTY_STRINGS.sub(replace_by, part)
    return out


def _create_element(element: str, text: str | None = None) -> html.HtmlElement:
    """
    Creates an lxml.html.HtmlElement without attaching it to a document tree.

    Args:
        element: The tag name for the new element (e.g., 'p', 'div').
        text: Optional text content for the element.

    Returns:
        An unparented lxml.html.HtmlElement.
    """

    new_element = html.HtmlElement()
    new_element.tag = element  # type: ignore
    if text:
        new_element.text = text  # type: ignore
    return new_element


def _wrap_figure(element: html.HtmlElement) -> html.HtmlElement:
    """
    Wraps a given lxml element within a <figure> element.

    Creates a new <figure> element, inserts it before the original element,
    moves the original element inside the <figure>, and removes the original
    element's tag and tail.

    Args:
        element: The lxml.html.HtmlElement to wrap.

    Returns:
        The newly created <figure> element containing the original element.
    """

    figure = _create_element("figure")
    element.addprevious(figure)  # type: ignore
    element.drop_tag()
    element.tail = ""  # type: ignore
    figure.append(element)  # type: ignore
    return figure


def join_following_elements(elements: list[html.HtmlElement], join_string: str = ""):
    """
    Joins consecutive elements from a list into the first element of the sequence.

    Iterates through the provided list. If an element is followed immediately
    by another element also present in the list, the following element is appended
    to the current element, its tag is dropped, and it's removed from the input list.
    Optional `join_string` is prepended to the text content of joined elements.

    Note: Modifies the input list `elements` in place.

    Args:
        elements: A list of lxml.html.HtmlElement objects to potentially join.
        join_string: A string to prepend to the text of elements being joined.
                     Defaults to "".
    """

    for element in elements:
        next_element = element.getnext()
        while next_element is not None and next_element in elements:
            current = next_element
            next_element = next_element.getnext()
            if current.text:
                current.text = join_string + current.text
            if current.tail:
                current.tail = current.tail.strip()
            element.append(current)  # type: ignore
            elements.remove(current)
            current.drop_tag()


def _fragments_from_string(html_string: str) -> list[html.HtmlElement]:
    """
    Parses an HTML string into a list of lxml.html.HtmlElement fragments.

    Handles potential leading text nodes by wrapping them in a <p> tag.
    Removes XML processing instructions.

    Args:
        html_string: The HTML string to parse.

    Returns:
        A list of top-level lxml.html.HtmlElement fragments parsed from the string.
        Returns an empty list if the string is empty or contains only whitespace.
    """

    fragments = html.fragments_fromstring(html_string)  # type: ignore
    fragments = cast(list[html.HtmlElement], fragments)

    if not len(fragments):
        return []
    # convert and append text node before starting tag
    if isinstance(fragments[0], str):
        if len(fragments[0].strip()) > 0:
            if len(fragments) == 1:
                return html.fragments_fromstring(f"<p>{fragments[0]}</p>")  # type: ignore
            else:
                paragraph = _create_element("p")
                paragraph.text = fragments[0]  # type: ignore
                fragments[1].addprevious(paragraph)  # type: ignore
                fragments.insert(1, paragraph)

        fragments.pop(0)
        if not len(fragments):
            return []

    # remove xml instructions (if cleaning is disabled)
    for instruction in fragments[0].xpath("//processing-instruction()"):  # type: ignore
        instruction.drop_tag()

    return fragments


def preprocess_media_tags(element: html.HtmlElement):  # noqa: C901
    """
    Preprocesses specific media-related tags within an lxml element tree.

    - Removes leading/trailing whitespace for <ul>/<ol> and <li> tags.
    - Converts <iframe> tags for YouTube, Vimeo, and Telegram embeds into
      Telegraph-compatible embed URLs and wraps them in <figure> tags if needed.
      Unsupported iframes are dropped.
    - Converts Twitter tweet blockquotes into Telegraph-compatible Twitter embed
      iframes based on links found within, wrapping them in <figure>.

    Args:
        element: The lxml.html.HtmlElement to process. Modifies the element
                 and its descendants in place.

    Raises:
        InvalidHTML: If the input `element` is not an lxml.html.HtmlElement.
    """

    try:
        assert isinstance(element, html.HtmlElement)
    except AssertionError:
        raise InvalidHTML("Element is not an instance of HtmlElement") from None

    if element.tag in ["ol", "ul"]:
        # ignore any spaces between <ul> and <li>
        element.text = ""  # type: ignore
    elif element.tag == "li":
        # ignore spaces after </li>
        element.tail = ""  # type: ignore
    elif element.tag == "iframe":
        iframe_src = element.get("src")  # type: ignore

        youtube = YOUTUBE_RE.match(iframe_src)  # type: ignore
        vimeo = VIMEO_RE.match(iframe_src)  # type: ignore
        telegram = TELEGRAM_EMBED_IFRAME_RE.match(iframe_src)  # type: ignore
        if youtube or vimeo or telegram:
            element.text = ""  # type: ignore
            if youtube:
                yt_id = urlparse(iframe_src).path.replace("/embed/", "")  # type: ignore
                element.set(  # type: ignore
                    "src",
                    "/embed/youtube?url="
                    + quote_plus("https://www.youtube.com/watch?v=" + yt_id),  # type: ignore
                )
            elif vimeo:
                element.set(  # type: ignore
                    "src",
                    "/embed/vimeo?url="
                    + quote_plus("https://vimeo.com/" + vimeo.group(2)),
                )
            elif telegram:
                element.set("src", "/embed/telegram?url=" + quote_plus(iframe_src))  # type: ignore
            if not len(element.xpath("./ancestor::figure")):  # type: ignore
                _wrap_figure(element)
        else:
            element.drop_tag()

    elif element.tag == "blockquote" and element.get("class") == "twitter-tweet":  # type: ignore
        twitter_links = element.xpath(".//a[@href]")  # type: ignore
        for tw_link in twitter_links:
            if TWITTER_RE.match(tw_link.get("href")):  # type: ignore
                twitter_frame = html.HtmlElement()
                twitter_frame.tag = "iframe"  # type: ignore
                twitter_frame.set(  # type: ignore
                    "src", "/embed/twitter?url=" + quote_plus(tw_link.get("href"))
                )
                element.addprevious(twitter_frame)  # type: ignore
                _wrap_figure(twitter_frame)
                element.drop_tree()
                break


def move_to_top(body: html.HtmlElement):
    """
    Moves <figure> and <blockquote> elements to the top level of the body.

    Identifies <figure> elements and <blockquote> elements nested within other tags
    (excluding direct children of the body). It moves these elements to become
    direct children of the `body` element, preserving the order relative to
    other top-level elements. Content preceding the moved element within its
    original parent is placed into a new container element of the same type
    as the original parent.

    Note: This function might have issues with deeply nested structures and
    modifies the `body` element in place.

    Args:
        body: The lxml.html.HtmlElement representing the main content body.
    """

    # TODO: include nested elements like lists
    elements = body.xpath("./*/figure|./*//blockquote")  # type: ignore

    for element in elements:
        preceding_elements: list[html.HtmlElement] = element.xpath(
            "./preceding-sibling::*"
        )  # type: ignore
        parent = element.getparent()
        if len(preceding_elements) > 0 or parent.text and len(parent.text) > 0:
            new_container = _create_element(parent.tag)  # type: ignore
            new_container.text = parent.text  # type: ignore
            parent.text = ""
            parent.addprevious(new_container)

            for preceding in preceding_elements:
                new_container.append(preceding)  # type: ignore

        parent_for_figure = element.xpath("./ancestor::*[parent::body]")[0]
        # tail leaves inside parent
        element.drop_tree()
        element.tail = ""
        parent_for_figure.addprevious(element)


def preprocess_fragments(fragments: list[html.HtmlElement]) -> html.HtmlElement | None:
    """
    Performs extensive preprocessing on a list of lxml fragments.

    - Adds line breaks to paragraphs within blockquotes/asides/figures if followed by siblings.
    - Removes empty tags (e.g., <iframe>, <img> without src, data URI images).
    - Removes non-text content from <figcaption>.
    - Removes all tags inside <pre>.
    - Removes empty list elements (ul, ol, li).
    - Removes links containing images.
    - Converts multi-line <code> blocks to <pre>.
    - Wraps elements not in ALLOWED_TOP_LEVEL_TAGS within <p> tags.
    - Wraps text nodes appearing between allowed top-level tags in <p> tags.
    - Wraps <img> tags not already inside a <figure> within a <figure> tag.

    Args:
        fragments: A list of lxml.html.HtmlElement fragments, typically obtained
                   from `_fragments_from_string`.

    Returns:
        The parent `lxml.html.HtmlElement` (body) containing the processed
        fragments, or None if the fragments list was empty or resulted in an
        empty body after processing.
    """
    bad_tags: list[html.HtmlElement] = []

    if not len(fragments):
        return None

    body = fragments[0].getparent()

    paras_inside_quote = body.xpath(
        ".//*[self::blockquote|self::aside|self::figure]//"
        "p[descendant-or-self::*[text()]][following-sibling::*[text()]]"
    )
    for para in paras_inside_quote:
        para.tail = "\n"

    bad_tags.extend(body.xpath(".//*[self::blockquote|self::aside]//p"))

    # remove empty iframes
    bad_tags.extend(body.xpath(".//iframe[not(@src)]|.//img[not(@src)]"))

    # remove images with data URIs
    bad_tags.extend(body.xpath('.//img[starts-with(normalize-space(@src), "data:")]'))

    # figcaption may have only text content
    bad_tags.extend(body.xpath(".//figcaption//*"))

    # drop all tags inside pre
    bad_tags.extend(body.xpath(".//pre//*"))

    # bad lists (remove lists/list items if empty)
    nodes_not_to_be_empty = body.xpath(".//ul|.//ol|.//li")
    bad_tags.extend(
        [x for x in nodes_not_to_be_empty if len(x.text_content().strip()) == 0]
    )
    # remove links with images inside
    bad_tags.extend(body.xpath(".//a[descendant::img]"))
    for bad_tag in set(bad_tags):
        bad_tag.drop_tag()

    # code - > pre
    # convert multiline code into pre
    code_elements = body.xpath(".//code")
    for code_element in code_elements:
        if "\n" in code_element.text_content():
            code_element.tag = "pre"

    for fragment in body.getchildren():
        if fragment.tag not in ALLOWED_TOP_LEVEL_TAGS:
            paragraph = _create_element("p")
            fragment.addprevious(paragraph)
            paragraph.append(fragment)  # type: ignore
        else:
            # convert and append text nodes after closing tag
            if fragment.tail and len(fragment.tail.strip()) != 0:
                paragraph = _create_element("p")
                paragraph.text = fragment.tail  # type: ignore
                fragment.tail = None
                fragment.addnext(paragraph)

    images_to_wrap = body.xpath(".//img[not(ancestor::figure)]")
    for image in images_to_wrap:
        _wrap_figure(image)

    return body if len(body.getchildren()) else None


def post_process(body: html.HtmlElement):
    """
    Performs final cleanup operations on the lxml element tree before conversion.

    - Removes tags listed in ELEMENTS_WITH_TEXT if they contain only whitespace.
    - Joins adjacent <pre> elements into a single <pre> element, separated by newlines.
    - Removes the 'class' attribute from all elements.
    - Removes <figure> elements that do not contain an <iframe>, <img>, <video>,
      or <figcaption>, and have no text content.

    Args:
        body: The lxml.html.HtmlElement representing the main content body.
              Modifies the element in place.
    """
    elements_not_empty = ".//*[{}]".format(
        "|".join(["self::" + x for x in ELEMENTS_WITH_TEXT])
    )
    bad_tags: list[html.HtmlElement] = body.xpath(elements_not_empty)  # type: ignore

    for x in bad_tags:
        if len(x.text_content().strip()) == 0:
            x.drop_tag()

    # group following pre elements into single one (telegraph is buggy)
    join_following_elements(body.xpath(".//pre"), join_string="\n")  # type: ignore

    # remove class attributes for all
    elements_with_class: list[html.HtmlElement] = body.xpath(".//*[@class]")  # type: ignore
    for element in elements_with_class:
        element.attrib.pop("class")

    # remove empty figure
    for x in body.xpath(  # type: ignore
        ".//figure[not(descendant::*[self::iframe|self::figcaption|self::img|self::video])]"
        "[not(normalize-space(text()))]"
    ):
        x.drop_tree()


def _recursive_convert(element: html.HtmlElement):
    """
    Recursively converts an lxml HTML element into the Telegraph node format.

    The Telegraph node format is a dictionary with keys 'tag', 'attrs' (optional),
    and 'children' (optional). Text content is represented as strings within the
    'children' list.

    Args:
        element: The lxml.html.HtmlElement to convert.

    Returns:
        A dictionary representing the element and its descendants in the
        Telegraph node format.
    """
    fragment_root_element = {"tag": element.tag}

    content: list[dict[str, Any]] = []
    if element.text:
        content.append(element.text)

    if element.attrib:
        fragment_root_element.update({"attrs": dict(element.attrib)})

    for child in element:  # type: ignore
        content.append(_recursive_convert(child))  # type: ignore
        # Append Text node after element, if exists
        if child.tail:  # type: ignore
            content.append(child.tail)  # type: ignore

    if len(content):
        fragment_root_element.update({"children": content})

    return fragment_root_element


def convert_html_to_telegraph_format(
    html_string: str,
    clean_html: bool = True,
    output_format: OutputFormat = OutputFormat.JSON_STRING,
) -> str | list[dict[str, Any]] | html.HtmlElement:
    """
    Converts an HTML string into the Telegraph API node format.

    This is the main function orchestrating the conversion process. It can optionally
    clean and preprocess the HTML before converting it to the final format.

    Steps:
    1. If `clean_html` is True (default):
       - Clean the HTML using `clean_article_html`.
       - Parse into fragments using `_fragments_from_string`.
       - Preprocess fragments using `preprocess_fragments`.
       - Apply media-specific preprocessing using `preprocess_media_tags`.
       - Move figures/blockquotes using `move_to_top`.
       - Perform final cleanup using `post_process`.
    2. If `clean_html` is False:
       - Parse into fragments using `_fragments_from_string`.
    3. Recursively convert the resulting lxml element tree (if any) into the
       Telegraph node format using `_recursive_convert`.
    4. Return the result according to the specified `output_format`.

    Args:
        html_string: The input HTML string.
        clean_html: Whether to perform cleaning and preprocessing steps. Defaults to True.
        output_format: The desired output format. Can be:
                       - OutputFormat.JSON_STRING (default): A JSON string representation.
                       - OutputFormat.PYTHON_LIST: A Python list of node dictionaries.
                       - OutputFormat.HTML_STRING: The processed HTML as a string (useful for debugging).

    Returns:
        The converted content in the specified format (JSON string, Python list,
        or HTML string). If the input HTML results in no content after processing,
        an empty list (for PYTHON_LIST) or its JSON equivalent ("[]") is returned.
        For HTML_STRING output, it returns the string representation of the processed
        lxml body element.
    """
    if clean_html:
        html_string = clean_article_html(html_string)

        body: html.HtmlElement | None = preprocess_fragments(
            _fragments_from_string(html_string)
        )
        if body is not None:
            desc: list[html.HtmlElement] = list(body.iterdescendants())  # type: ignore
            for tag in desc:
                preprocess_media_tags(tag)
            move_to_top(body)
            post_process(body)
    else:
        fragments = _fragments_from_string(html_string)
        body: html.HtmlElement | None = (
            fragments[0].getparent() if len(fragments) else None
        )

    content: list[dict[str, Any]] = []
    if body is not None:
        content = [_recursive_convert(x) for x in body.iterchildren()]  # type: ignore

    if output_format == OutputFormat.JSON_STRING:
        return json.dumps(content, ensure_ascii=False)
    elif output_format == OutputFormat.PYTHON_LIST:
        return content
    elif output_format == OutputFormat.HTML_STRING:
        return cast(str, html.tostring(body, encoding="unicode"))  # type: ignore
