class TelegraphAPIError(Exception):
    """Custom exception for Telegraph API errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class InvalidHTML(Exception):
    """Custom exception for invalid HTML."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class NotAllowedTag(Exception):
    """Custom exception for not allowed tags."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)