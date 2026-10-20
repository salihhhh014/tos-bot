import asyncio

from tos_bot.services.quota import Quota


def test_quota_allows_up_to_limit(tmp_path):
    q = Quota(str(tmp_path / "q.db"), daily_limit=3)
    for _ in range(3):
        assert asyncio.run(q.check_and_hit(1))[0] is True
    ok, left = asyncio.run(q.check_and_hit(1))
    assert ok is False
    assert left == 0


def test_quota_per_user(tmp_path):
    q = Quota(str(tmp_path / "q.db"), daily_limit=1)
    assert asyncio.run(q.check_and_hit(1))[0] is True
    assert asyncio.run(q.check_and_hit(1))[0] is False
    # другой юзер — свой счетчик
    assert asyncio.run(q.check_and_hit(2))[0] is True


def test_quota_zero_means_off(tmp_path):
    q = Quota(str(tmp_path / "q.db"), daily_limit=0)
    for _ in range(5):
        assert asyncio.run(q.check_and_hit(9))[0] is True


def test_refund_gives_attempt_back(tmp_path):
    q = Quota(str(tmp_path / "q.db"), daily_limit=1)
    assert asyncio.run(q.check_and_hit(1))[0] is True
    assert asyncio.run(q.check_and_hit(1))[0] is False
    asyncio.run(q.refund(1))
    assert asyncio.run(q.check_and_hit(1))[0] is True


def test_refund_below_zero_safe(tmp_path):
    q = Quota(str(tmp_path / "q.db"), daily_limit=1)
    asyncio.run(q.refund(5))  # ничего не жгли — просто не падаем
    assert asyncio.run(q.check_and_hit(5))[0] is True
