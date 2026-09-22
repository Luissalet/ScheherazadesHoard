"""Unit tests for the pure dice engine."""
from __future__ import annotations

import pytest

from scheherazades_hoard import dice


def test_constant():
    r = dice.roll("10")
    assert r.total == 10
    assert r.dice == []


def test_simple_ndm():
    r = dice.roll("2d6+3", seed=1)
    assert 5 <= r.total <= 15
    assert len(r.dice) == 2
    assert all(1 <= d.value <= 6 for d in r.dice)


def test_subtraction_between_dice_terms():
    r = dice.roll("2d6-1d4", seed=1)
    two_d6 = sum(d.value for d in r.dice if d.sides == 6)
    one_d4 = sum(d.value for d in r.dice if d.sides == 4)
    assert r.total == two_d6 - one_d4


def test_keep_highest():
    r = dice.roll("4d6kh3", seed=5)
    kept = [d for d in r.dice if d.kept]
    dropped = [d for d in r.dice if not d.kept]
    assert len(kept) == 3
    assert len(dropped) == 1
    assert r.total == sum(d.value for d in kept)
    assert min(d.value for d in kept) >= dropped[0].value


def test_keep_lowest():
    r = dice.roll("4d6kl2", seed=5)
    kept = [d for d in r.dice if d.kept]
    assert len(kept) == 2
    assert r.total == sum(d.value for d in kept)


def test_drop_highest():
    r = dice.roll("4d6dh1", seed=5)
    kept = [d for d in r.dice if d.kept]
    assert len(kept) == 3


def test_drop_lowest():
    r = dice.roll("4d6dl1", seed=5)
    kept = [d for d in r.dice if d.kept]
    assert len(kept) == 3


def test_exploding_die_chains_on_max():
    # d1 always rolls its max (1) -> guaranteed to explode repeatedly.
    r = dice.roll("1d1!", seed=1)
    assert r.total == dice.MAX_EXPLOSIONS
    assert len(r.dice) == dice.MAX_EXPLOSIONS
    assert r.dice[0].exploded_from is False
    assert all(d.exploded_from for d in r.dice[1:])


def test_exploding_die_does_not_explode_below_max():
    r = dice.roll("1d20!", seed=2)
    if r.dice[0].value != 20:
        assert len(r.dice) == 1


def test_fate_dice_range():
    r = dice.roll("4dF", seed=3)
    assert len(r.dice) == 4
    assert all(d.value in (-1, 0, 1) for d in r.dice)
    assert r.total == sum(d.value for d in r.dice)


def test_fate_dice_cannot_explode():
    with pytest.raises(dice.DiceError):
        dice.roll("4dF!")


def test_advantage():
    r = dice.roll("adv(d20)", seed=9)
    assert len(r.dice) == 2
    kept = [d for d in r.dice if d.kept]
    assert len(kept) == 1
    assert r.total == kept[0].value
    assert kept[0].value == max(d.value for d in r.dice)


def test_disadvantage():
    r = dice.roll("dis(d20)", seed=9)
    kept = [d for d in r.dice if d.kept]
    assert kept[0].value == min(d.value for d in r.dice)


def test_advantage_with_modifier():
    r = dice.roll("adv(d20)+5", seed=9)
    kept = [d for d in r.dice if d.kept]
    assert r.total == kept[0].value + 5


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "2x6",
        "0d6",
        "101d6",
        "1d1001",
        "d6kh2",
        "adv(6)",
        "dis(6)",
        "2d6 3",
        "++2d6",
        "2d6++3",
        "4dF!",
        "5d6kh10",
    ],
)
def test_invalid_expressions_raise(bad):
    with pytest.raises(dice.DiceError):
        dice.roll(bad)


def test_non_string_expression_raises():
    with pytest.raises(dice.DiceError):
        dice.roll(None)  # type: ignore[arg-type]


def test_seeded_reproducibility():
    a = dice.roll("4d6kh3+2", seed=12345)
    b = dice.roll("4d6kh3+2", seed=12345)
    assert a.total == b.total
    assert [d.value for d in a.dice] == [d.value for d in b.dice]


def test_unseeded_uses_system_random_and_varies():
    totals = {dice.roll("20d6").total for _ in range(8)}
    assert len(totals) > 1  # astronomically unlikely to collide 8/8 times


def test_default_die_count_is_one():
    r = dice.roll("d6", seed=1)
    assert len(r.dice) == 1


def test_bounds_are_inclusive():
    dice.roll("100d1", seed=1)  # 100 dice: upper bound, must not raise
    dice.roll("1d1000", seed=1)  # 1000 sides: upper bound, must not raise
    dice.roll("1d1", seed=1)  # 1 side: lower bound, must not raise


# --- regressions found in review ------------------------------------------

@pytest.mark.parametrize("bad", [
    "99999999999999999999999",          # overflowed SQLite INTEGER -> HTTP 500
    "2d6+" + "1" * 30,
    "+".join(["100d1000"] * 3),          # 300 dice asked for
    "+".join(["1d6"] * 21),              # too many terms
    "1d6" + "+1" * 60,                   # too long
    "100d1!",                            # explodes past the rolled-dice cap
])
def test_resource_bounds(bad):
    with pytest.raises(dice.DiceError):
        dice.roll(bad, seed=1)


def test_band_and_crit_interpretation():
    assert dice.interpret(dice.roll("2d6+1", seed=101), "pbta_2d6") == {"band": "weak_hit"}
    assert dice.interpret(dice.roll("2d6+1", seed=101), "d20") == {}
    r = dice.roll("adv(d20)+3", seed=5)
    info = dice.interpret(r, "d20")
    assert info["natural"] == max(d.value for d in r.dice)
    assert dice.interpret(dice.roll("3d6", seed=1), "pbta_2d6") == {}
