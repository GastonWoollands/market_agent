import time

from ingest.yahoo.rate_limit import TokenBucket


def test_token_bucket_does_not_block_when_tokens_available() -> None:
    bucket = TokenBucket(rate=100.0, burst=2)
    started = time.monotonic()
    bucket.acquire()
    bucket.acquire()
    elapsed = time.monotonic() - started
    assert elapsed < 0.05
