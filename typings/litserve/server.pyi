from collections.abc import Coroutine

from litserve import LitAPIConnector, LitTransport, ResponseBufferItem

def response_queue_to_buffer(
    transport: LitTransport,
    response_buffer: dict[str, ResponseBufferItem],
    consumer_id: int,
    litapi_connector: LitAPIConnector,
) -> Coroutine[None, None, None]: ...
