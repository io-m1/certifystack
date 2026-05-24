class CertificateEngineError(Exception):
    """Base exception for all certificate engine errors."""


class TemplateValidationError(CertificateEngineError):
    """Template is invalid: missing required fields, malformed SVG, etc."""


class MissingFieldError(CertificateEngineError):
    """A required field ID was not found in the template."""


class ConversionError(CertificateEngineError):
    """SVG to PDF/PNG conversion failed."""


class FontError(CertificateEngineError):
    """Font loading, matching, or fallback issue."""
