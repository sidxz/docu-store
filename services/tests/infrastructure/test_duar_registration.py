"""register_service_actions is best-effort: a slow/locked Duar must never
block application boot. Moving actions out of the Duar(...) ctor (where the
SDK lifespan registers them fatally) is the whole point — guard it here.
"""

import httpx
import pytest

from infrastructure import auth


class _Roles:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.calls = 0

    async def register_actions(self, actions):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return list(actions)


class _Duar:
    def __init__(self, exc: Exception | None = None) -> None:
        self.roles = _Roles(exc)


@pytest.mark.asyncio
async def test_successful_registration_returns_true():
    duar = _Duar()
    assert await auth.register_service_actions(duar) is True
    assert duar.roles.calls == 1


@pytest.mark.asyncio
async def test_readtimeout_is_swallowed_so_boot_continues():
    # The exact failure mode: Duar accepts the connection but the
    # registration POST never returns within the SDK timeout.
    duar = _Duar(exc=httpx.ReadTimeout("duar hung"))
    assert await auth.register_service_actions(duar) is False
    assert duar.roles.calls == 1


@pytest.mark.asyncio
async def test_arbitrary_error_is_swallowed():
    duar = _Duar(exc=RuntimeError("unexpected"))
    assert await auth.register_service_actions(duar) is False
