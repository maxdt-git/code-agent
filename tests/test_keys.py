import pytest
from agent_smith.llm.keys import KeyPool, load_keys


# --- Load_keys

def test_sorted_by_number_not_by_name() -> None:
    env = {"P_10": "a", "P_2": "b", "P_1": "c"}
    assert load_keys("P", env) == [("P_1", "c"), ("P_2", "b"), ("P_10", "a")]


def test_unsuffixed_key_comes_first() -> None:
    env = {"P_1": "a", "P": "z"}
    assert load_keys("P", env) == [("P", "z"), ("P_1", "a")]


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_empty_and_blank_values_ignored(value: str) -> None:
    assert load_keys("P", {"P_1": value}) == []


def test_values_are_stripped() -> None:
    assert load_keys("P", {"P_1": "  a \n"}) == [("P_1", "a")]


def test_duplicate_keeps_lowest_number() -> None:
    env = {"P_4": "a", "P_1": "a", "P_2": "b"}
    assert load_keys("P", env) == [("P_1", "a"), ("P_2", "b")]


@pytest.mark.parametrize("name", ["P_OLD", "P_", "P_1a", "PX_1", "XP_1"])
def test_invalid_names_rejected(name: str) -> None:
    assert load_keys("P", {name: "a"}) == []


def test_other_variables_ignored() -> None:
    env = {"HOME": "/home/me", "PATH": "/usr/bin", "P_1": "a"}
    assert load_keys("P", env) == [("P_1", "a")]


# --- KeyPool

def make_pool() -> KeyPool:
    return KeyPool("P", {"P_1": "a", "P_2": "b", "P_3": "c"})


def test_current_starts_at_first_key() -> None:
    assert make_pool().current() == ("P_1", "a")


def test_rotate_moves_to_next_key() -> None:
    pool = make_pool()
    pool.rotate()
    assert pool.current() == ("P_2", "b")


def test_rotate_wraps_around() -> None:
    pool = make_pool()
    for _ in range(3):
        pool.rotate()
    assert pool.current() == ("P_1", "a")


def test_disable_current_moves_to_next_key() -> None:
    pool = make_pool()
    pool.disable_current()
    assert pool.current() == ("P_2", "b")
    assert pool.live_count == 2


def test_rotate_skips_disabled_keys() -> None:
    pool = make_pool()
    pool.rotate()
    pool.disable_current()
    pool.rotate()
    pool.rotate()
    assert pool.current() == ("P_3", "c")


def test_all_disabled_returns_none() -> None:
    pool = make_pool()
    for _ in range(3):
        pool.disable_current()
    assert pool.current() is None
    assert pool.live_count == 0


def test_calls_on_dead_pool_do_not_crash() -> None:
    pool = make_pool()
    for _ in range(3):
        pool.disable_current()
    pool.rotate()
    pool.disable_current()
    assert pool.current() is None
    assert pool.live_count == 0


def test_empty_pool_does_not_crash() -> None:
    pool = KeyPool("P", {})
    assert pool.current() is None
    pool.rotate()
    pool.disable_current()
    assert pool.current() is None
    assert pool.live_count == 0


def test_single_key_rotate_stays_on_it() -> None:
    pool = KeyPool("P", {"P_1": "a"})
    pool.rotate()
    assert pool.current() == ("P_1", "a")
