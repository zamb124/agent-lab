from datetime import datetime
from types import TracebackType
from typing import Literal, Required, TypedDict, Unpack

from botocore.config import Config

S3PresignedMethod = Literal["get_object", "put_object"]


class S3ObjectRequest(TypedDict):
    Bucket: str
    Key: str


class S3CopySource(TypedDict):
    Bucket: str
    Key: str


class S3UploadExtraArgs(TypedDict, total=False):
    Metadata: dict[str, str]
    ContentType: str
    ACL: Literal["public-read"]


class S3PutObjectRequest(TypedDict, total=False):
    Bucket: Required[str]
    Key: Required[str]
    Body: Required[bytes]
    Metadata: dict[str, str]
    ContentType: str
    ACL: Literal["public-read"]


class S3GetObjectRequest(TypedDict, total=False):
    Bucket: Required[str]
    Key: Required[str]
    Range: str


class S3ObjectBody:
    async def read(self, amt: int | None = ...) -> bytes: ...
    def close(self) -> None: ...


class S3GetObjectResponse(TypedDict):
    Body: S3ObjectBody


class S3HeadObjectResponse(TypedDict):
    ContentType: str
    ContentLength: int
    LastModified: datetime
    ETag: str
    Metadata: dict[str, str]


class S3ListedObjectResponse(TypedDict):
    Key: str
    Size: int
    LastModified: datetime
    ETag: str


class S3ListObjectsV2Response(TypedDict, total=False):
    Contents: list[S3ListedObjectResponse]


class S3ServiceClient:
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def head_bucket(self, *, Bucket: str) -> None: ...
    async def create_bucket(self, *, Bucket: str) -> None: ...
    async def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        *,
        ExtraArgs: S3UploadExtraArgs | None = ...,
    ) -> None: ...
    async def put_object(self, **kwargs: Unpack[S3PutObjectRequest]) -> None: ...
    async def download_file(self, Bucket: str, Key: str, Filename: str) -> None: ...
    async def get_object(self, **kwargs: Unpack[S3GetObjectRequest]) -> S3GetObjectResponse: ...
    async def delete_object(self, *, Bucket: str, Key: str) -> None: ...
    async def head_object(self, *, Bucket: str, Key: str) -> S3HeadObjectResponse: ...
    async def generate_presigned_url(
        self,
        ClientMethod: S3PresignedMethod,
        *,
        Params: S3ObjectRequest,
        ExpiresIn: int,
    ) -> str: ...
    async def list_objects_v2(
        self,
        *,
        Bucket: str,
        Prefix: str,
        MaxKeys: int,
        StartAfter: str = ...,
    ) -> S3ListObjectsV2Response: ...
    async def copy_object(self, *, CopySource: S3CopySource, Bucket: str, Key: str) -> None: ...


class S3ClientContextManager:
    async def __aenter__(self) -> S3ServiceClient: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class Session:
    def client(
        self,
        service_name: Literal["s3"],
        *,
        region_name: str | None = ...,
        api_version: str | None = ...,
        use_ssl: bool = ...,
        verify: bool | str | None = ...,
        endpoint_url: str | None = ...,
        aws_access_key_id: str | None = ...,
        aws_secret_access_key: str | None = ...,
        aws_session_token: str | None = ...,
        config: Config | None = ...,
        aws_account_id: str | None = ...,
    ) -> S3ClientContextManager: ...
