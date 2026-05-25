from typing import TypedDict

class ClientErrorDetail(TypedDict):
    Code: str
    Message: str


class ClientErrorMetadata(TypedDict):
    HTTPStatusCode: int


class ClientErrorResponse(TypedDict):
    Error: ClientErrorDetail
    ResponseMetadata: ClientErrorMetadata


class ClientError(Exception):
    response: ClientErrorResponse

    def __init__(self, error_response: ClientErrorResponse, operation_name: str) -> None: ...
