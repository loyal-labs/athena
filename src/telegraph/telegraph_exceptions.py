class TelegraphAPIError(Exception):
    """Custom exception for Telegraph API errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
