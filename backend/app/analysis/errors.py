"""خطاهای قابل‌نمایش به کاربر از سمت مدل زبانی (بدون محتوای مکالمه)."""
from __future__ import annotations


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message
