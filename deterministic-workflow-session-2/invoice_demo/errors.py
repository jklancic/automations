"""Safe error messages: never expose raw SDK exceptions or model payloads."""


class DemoError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
