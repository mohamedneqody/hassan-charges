"""Shared exceptions with user-facing messages."""


class AppError(Exception):
    """Base error carrying a user-facing English message."""


class UnsupportedFormatError(AppError):
    def __init__(self) -> None:
        super().__init__("Unsupported file format. Supported formats: PDF, CSV, XLSX, XLS.")


class EmptyFileError(AppError):
    def __init__(self) -> None:
        super().__init__("The uploaded file is empty.")


class InsufficientDataError(AppError):
    def __init__(self, detail: str = "") -> None:
        msg = "Insufficient financial data for analysis."
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class ExtractionError(AppError):
    """Raised when a supported file cannot be parsed at all."""

    def __init__(self, detail: str = "") -> None:
        msg = "Could not read the financial statements from this file."
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)
