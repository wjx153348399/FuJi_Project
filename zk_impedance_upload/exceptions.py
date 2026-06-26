class ZKUploadError(Exception):
    """Base error for the upload script."""


class ConfigError(ZKUploadError):
    """Raised when the configuration file is missing or invalid."""


class LogError(ZKUploadError):
    """Raised when log files cannot be read or written safely."""
