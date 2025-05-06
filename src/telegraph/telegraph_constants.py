import re

ALLOWED_TAGS = (
    "a",
    "aside",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h3",
    "h4",
    "hr",
    "i",
    "iframe",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
    "video",
)
ALLOWED_TOP_LEVEL_TAGS = (
    "aside",
    "blockquote",
    "pre",
    "figure",
    "h3",
    "h4",
    "hr",
    "ol",
    "p",
    "ul",
)

ELEMENTS_WITH_TEXT = ("a", "aside", "b", "blockquote", "em", "h3", "h4", "p", "strong")

YOUTUBE_RE = re.compile(r"(https?:)?//(www\.)?youtube(-nocookie)?\.com/embed/")
VIMEO_RE = re.compile(r"(https?:)?//player\.vimeo\.com/video/(\d+)")
TWITTER_RE = re.compile(
    r"(https?:)?//(www\.)?twitter\.com/[A-Za-z0-9_]{1,15}/status/\d+"
)
TELEGRAM_EMBED_IFRAME_RE = re.compile(
    r"^(https?)://(t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]+)/(\d+)",
    re.IGNORECASE,
)
TELEGRAM_EMBED_SCRIPT_RE = re.compile(
    r"""<script(?=[^>]+\sdata-telegram-post=['"]([^'"]+))[^<]+</script>""",
    re.IGNORECASE,
)
PRE_CONTENT_RE = re.compile(r"<(pre|code)(>|\s[^>]*>)[\s\S]*?</\1>")
LINE_BREAKS_INSIDE_PRE = re.compile(r"<br(/?>|\s[^<>]*>)")
LINE_BREAKS_AND_EMPTY_STRINGS = re.compile(r"(\s{2,}|\s*\r?\n\s*)")
HEADER_RE = re.compile(r"<head[^a-z][\s\S]*</head>")
