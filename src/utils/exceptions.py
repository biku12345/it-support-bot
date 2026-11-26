class ITSupportError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class ConfigurationError(ITSupportError):
    pass

class RetrievalError(ITSupportError):
    pass

class VectorDBConnectionError(RetrievalError):
    pass

class VectorDBQueryError(RetrievalError):
    pass

class WebSearchError(RetrievalError):
    pass

class LLMError(ITSupportError):
    pass

class LLMQuotaError(LLMError):
    pass

class LLMTimeoutError(LLMError):
    pass

class IngestionError(ITSupportError):
    pass

class S3AccessError(IngestionError):
    pass

class DocumentParseError(IngestionError):
    pass

class SessionError(ITSupportError):
    pass
