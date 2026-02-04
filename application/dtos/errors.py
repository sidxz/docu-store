class AppError:
    """Represents different categories of application errors."""

    def __init__(self, category: str, message: str) -> None:
        self.category = category  # 'validation', 'not_found', 'concurrency', 'infrastructure'
        self.message = message

    def __str__(self) -> str:
        return self.message
