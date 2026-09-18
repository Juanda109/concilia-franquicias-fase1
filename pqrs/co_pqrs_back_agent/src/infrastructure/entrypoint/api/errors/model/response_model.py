from pydantic import BaseModel


class ExceptionResponse(BaseModel):
    id: str
    status: int
    error: str
    detail: str
