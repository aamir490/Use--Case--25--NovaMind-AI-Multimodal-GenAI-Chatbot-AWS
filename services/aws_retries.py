"""Bounded retries for AWS operations that are safe to repeat as reads."""
import time

from botocore.exceptions import (
    ClientError, ConnectTimeoutError, ConnectionClosedError, EndpointConnectionError,
    IncompleteReadError, ReadTimeoutError,
)

RETRYABLE_CODES = frozenset({
    "InternalFailure", "InternalServerError", "LimitExceededException",
    "PriorRequestNotComplete", "RequestLimitExceeded", "RequestThrottled",
    "RequestThrottledException",
    "RequestTimeout", "RequestTimeoutException", "ServiceUnavailable",
    "ServiceUnavailableException", "SlowDown", "Throttling", "ThrottlingException",
    "TooManyRequestsException", "ProvisionedThroughputExceededException",
})
RETRYABLE_TRANSPORT_ERRORS = (
    ConnectTimeoutError, ConnectionClosedError, EndpointConnectionError,
    IncompleteReadError, ReadTimeoutError,
)


def retry_read(operation, *, attempts=3, sleep=None):
    """Retry transient reads at most three times with short exponential backoff."""
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("Read retries are limited to three attempts.")
    sleep = time.sleep if sleep is None else sleep
    for attempt in range(attempts):
        try:
            return operation()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in RETRYABLE_CODES or attempt + 1 == attempts:
                raise
        except RETRYABLE_TRANSPORT_ERRORS:
            if attempt + 1 == attempts:
                raise
        sleep(min(0.1 * (2 ** attempt), 0.5))
