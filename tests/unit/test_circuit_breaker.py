import time

import pytest

from resilience.circuit_breaker import CircuitBreaker, CircuitOpenError, circuit_breaker


async def fail(name="svc", **kw):
    with pytest.raises(RuntimeError):
        async with circuit_breaker(name, **kw):
            raise RuntimeError("boom")


async def test_starts_closed(fake_redis):
    assert (await CircuitBreaker("svc").status())["state"] == "closed"


async def test_opens_after_five_failures(fake_redis):
    for _ in range(5):
        await fail()
    assert (await CircuitBreaker("svc").status())["state"] == "open"


async def test_open_circuit_rejects_calls(fake_redis):
    for _ in range(5):
        await fail()
    with pytest.raises(CircuitOpenError):
        async with circuit_breaker("svc"):
            pass


async def test_four_failures_stay_closed(fake_redis):
    for _ in range(4):
        await fail()
    assert (await CircuitBreaker("svc").status())["state"] == "closed"


async def test_half_open_after_timeout_then_closes_on_success(fake_redis):
    for _ in range(5):
        await fail()
    fake_redis.store["circuit:svc:opened_at"] = str(time.time() - 100)
    async with circuit_breaker("svc", recovery_timeout=60):
        assert fake_redis.store["circuit:svc:state"] == "half_open"
    assert (await CircuitBreaker("svc").status())["state"] == "closed"


async def test_half_open_failure_reopens(fake_redis):
    for _ in range(5):
        await fail()
    fake_redis.store["circuit:svc:opened_at"] = str(time.time() - 100)
    await fail(recovery_timeout=60)
    assert (await CircuitBreaker("svc").status())["state"] == "open"


async def test_half_open_limits_calls(fake_redis):
    fake_redis.store["circuit:svc:state"] = "half_open"
    fake_redis.store["circuit:svc:half_open_calls"] = "3"
    with pytest.raises(CircuitOpenError):
        async with circuit_breaker("svc", half_open_max_calls=3):
            pass