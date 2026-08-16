"""Fact Store 可用性 provider 的行为测试。"""


def test_provider_reconnects_after_cooldown():
    """一次连接失败不能永久禁用 KB，冷却结束后应自动恢复。"""
    from agent.kb.provider import FactStoreProvider

    now = [100.0]
    attempts = []
    recovered_store = object()

    def factory():
        attempts.append(now[0])
        if len(attempts) == 1:
            raise ConnectionError("milvus unavailable")
        return recovered_store

    provider = FactStoreProvider(
        factory=factory,
        retry_interval_seconds=30,
        clock=lambda: now[0],
    )

    assert provider.get() is None
    assert provider.get() is None
    assert attempts == [100.0]

    now[0] = 131.0
    assert provider.get() is recovered_store
    assert attempts == [100.0, 131.0]


def test_invalid_retry_interval_uses_safe_cooldown(monkeypatch):
    from agent.kb.provider import FactStoreProvider

    monkeypatch.setenv("KB_RECONNECT_INTERVAL_SECONDS", "nan")
    attempts = []

    def factory():
        attempts.append(1)
        raise ConnectionError("milvus unavailable")

    provider = FactStoreProvider(factory=factory, clock=lambda: 100.0)

    assert provider.get() is None
    assert provider.get() is None
    assert attempts == [1]
