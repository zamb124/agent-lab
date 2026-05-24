from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import TypeAlias

JWTScalar: TypeAlias = str | int | float | bool | None
JWTValue: TypeAlias = JWTScalar | Mapping[str, "JWTValue"] | Sequence["JWTValue"]
JWTEncodeScalar: TypeAlias = JWTScalar | datetime
JWTEncodeValue: TypeAlias = (
    JWTEncodeScalar | Mapping[str, "JWTEncodeValue"] | Sequence["JWTEncodeValue"]
)
JWTPayload: TypeAlias = dict[str, JWTValue]


class PyJWTError(Exception): ...
class DecodeError(PyJWTError): ...
class ExpiredSignatureError(DecodeError): ...
class InvalidTokenError(PyJWTError): ...


class PyJWK:
    key: str


class PyJWKClient:
    def __init__(self, uri: str) -> None: ...
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


def encode(
    payload: Mapping[str, JWTEncodeValue],
    key: str | bytes,
    algorithm: str | None = ...,
    headers: Mapping[str, JWTEncodeValue] | None = ...,
    sort_headers: bool = ...,
) -> str: ...


def decode(
    jwt: str | bytes,
    key: str | bytes = ...,
    algorithms: Sequence[str] | None = ...,
    options: Mapping[str, JWTValue] | None = ...,
    audience: str | Sequence[str] | None = ...,
    issuer: str | Sequence[str] | None = ...,
    leeway: float | timedelta = ...,
) -> JWTPayload: ...


def get_unverified_header(jwt: str | bytes) -> JWTPayload: ...
