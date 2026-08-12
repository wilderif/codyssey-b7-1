"""Chat domain이 HTTP layer에 전달하는 안전한 오류다."""


class AppError(Exception):
    """JSON API가 안전하게 응답할 수 있는 application 오류다."""

    def __init__(
        self, *, status_code: int, code: str, detail_key: str | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail_key = detail_key or code
        super().__init__(code)


class ChatError(Exception):
    """사용자 응답으로 변환 가능한 Chat domain 오류의 base class다."""


class ChatGenerationError(ChatError):
    """OpenAI 답변을 생성하지 못했다."""

    record_message = "openai_api_error"


class ChatTimeoutError(ChatGenerationError):
    """OpenAI 호출 시간이 초과됐다."""

    record_message = "openai_timeout"


class ChatInvalidResponseError(ChatGenerationError):
    """OpenAI response에 사용할 수 있는 text answer가 없다."""

    record_message = "openai_api_error"


class ChatConfigurationError(ChatError):
    """OpenAI 호출에 필요한 server 설정이 없다."""


class ChatPersistenceError(ChatError):
    """ChatExchange read 또는 write transaction이 실패했다."""

    def __init__(self, *, is_write: bool = True) -> None:
        self.is_write = is_write
        super().__init__("write" if is_write else "read")
