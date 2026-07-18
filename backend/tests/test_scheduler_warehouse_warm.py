from app.core.scheduler import _warehouse_needs_warm


def test_empty_pool_requires_startup_warm():
    assert _warehouse_needs_warm(fresh_pool_jobs=0, live_canonical_jobs=10)


def test_empty_canonical_warehouse_requires_startup_warm():
    assert _warehouse_needs_warm(fresh_pool_jobs=100, live_canonical_jobs=0)


def test_thin_production_warehouse_requires_startup_warm():
    assert _warehouse_needs_warm(fresh_pool_jobs=19, live_canonical_jobs=19)


def test_low_search_supply_requires_startup_warm():
    assert _warehouse_needs_warm(fresh_pool_jobs=99, live_canonical_jobs=80)


def test_low_recommendation_supply_requires_startup_warm():
    assert _warehouse_needs_warm(fresh_pool_jobs=100, live_canonical_jobs=49)


def test_populated_warehouse_skips_startup_warm():
    assert not _warehouse_needs_warm(fresh_pool_jobs=100, live_canonical_jobs=80)
