"""A pure dice engine: parsing, rolling, and small tabletop ruleset helpers.

No I/O, no imports from the rest of the package. Deterministic when given a
seed (`random.Random(seed)`), cryptographically random otherwise
(`secrets.SystemRandom`), so results can be reproduced for debugging but
are not predictable by default.

Grammar (case-insensitive, whitespace ignored)::

    expr        := term (('+' | '-') term)*
    term        := INT | dice_term | adv_term
    dice_term   := [INT] 'd' (INT | 'F') ['!'] [keepdrop]
    keepdrop    := ('kh' | 'kl' | 'dh' | 'dl') INT
    adv_term    := ('adv' | 'dis') '(' 'd' INT ')'

Examples: ``2d6+3``, ``4d6kh3``, ``1d20!``, ``adv(d20)+5``, ``4dF``.

Bounds (an agent or a pasted string must not be able to make the app roll
a million dice or overflow SQLite's 64-bit integers): at most 100
characters, 20 terms, 200 dice asked for, 1000 dice rolled including
explosions, constants up to 10000, 100 dice and 1000 sides per term.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from random import Random
from typing import Optional, Union

MAX_DICE_PER_TERM = 100
MAX_SIDES = 1000
MAX_EXPLOSIONS = 100  # safety cap on a single die's explosion chain
MAX_EXPRESSION_CHARS = 100
MAX_TERMS = 20
MAX_CONSTANT = 10_000
MAX_TOTAL_DICE = 200  # dice asked for across all terms, before explosions
MAX_ROLLED_DICE = 1000  # dice actually rolled, explosions included


class DiceError(ValueError):
    """Raised for a malformed or out-of-bounds dice expression."""


@dataclass
class Die:
    sides: Union[int, str]  # int, or "F" for a fate die
    value: int
    kept: bool = True
    exploded_from: bool = False  # this die exists because a prior one exploded

    def to_dict(self) -> dict:
        return {
            "sides": self.sides,
            "value": self.value,
            "kept": self.kept,
            "exploded_from": self.exploded_from,
        }


@dataclass
class DiceResult:
    expression: str
    total: int
    dice: list[Die] = field(default_factory=list)
    seed: Optional[int] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "total": self.total,
            "dice": [d.to_dict() for d in self.dice],
            "seed": self.seed,
            "detail": self.detail,
        }


_TERM_SPLIT_RE = re.compile(r"[+-]?\s*[^+\-\s][^+-]*")
_ADV_RE = re.compile(r"^(adv|dis)\(\s*d(\d+)\s*\)$", re.IGNORECASE)
_DICE_RE = re.compile(
    r"^(\d*)d(f|\d+)(!)?((?:kh|kl|dh|dl)\d+)?$", re.IGNORECASE
)
_INT_RE = re.compile(r"^\d+$")


def _split_terms(expression: str) -> list[str]:
    cleaned = expression.strip()
    if not cleaned:
        raise DiceError("empty expression")
    # Whitespace directly around a '+'/'-' operator is cosmetic ("2d6 + 3");
    # any other whitespace makes the expression ambiguous ("2d6 3") and is
    # rejected rather than silently glued into one token.
    collapsed = re.sub(r"\s*([+-])\s*", r"\1", cleaned)
    if re.search(r"\s", collapsed):
        raise DiceError(f"cannot parse expression: {expression!r}")
    if not re.match(r"^[+-]?\S", collapsed):
        raise DiceError(f"cannot parse expression: {expression!r}")
    chunks = _TERM_SPLIT_RE.findall(collapsed)
    if not chunks:
        raise DiceError(f"cannot parse expression: {expression!r}")
    joined = "".join(chunks)
    if joined != collapsed:
        raise DiceError(f"cannot parse expression: {expression!r}")
    return chunks


def _roll_die(rng: Random, sides: Union[int, str]) -> int:
    if sides == "F":
        return rng.choice((-1, 0, 1))
    return rng.randint(1, sides)


def _is_max(value: int, sides: Union[int, str]) -> bool:
    if sides == "F":
        return False  # fate dice don't explode
    return value == sides


def _roll_logical_die(rng: Random, sides: Union[int, str], explode: bool) -> list[Die]:
    """Roll one die, following its explosion chain. Returns 1+ Die entries."""
    chain: list[Die] = []
    value = _roll_die(rng, sides)
    chain.append(Die(sides=sides, value=value))
    count = 1
    while explode and _is_max(value, sides) and count < MAX_EXPLOSIONS:
        value = _roll_die(rng, sides)
        chain.append(Die(sides=sides, value=value, exploded_from=True))
        count += 1
    return chain


def _parse_keepdrop(token: Optional[str]) -> Optional[tuple[str, int]]:
    if not token:
        return None
    mode = token[:2].lower()
    n = int(token[2:])
    if n < 1:
        raise DiceError(f"keep/drop count must be >= 1: {token!r}")
    return mode, n


def _apply_keepdrop(logical_values: list[int], keepdrop: Optional[tuple[str, int]]) -> list[bool]:
    """Return a `kept` flag per logical die, index-aligned with logical_values."""
    n = len(logical_values)
    kept = [True] * n
    if keepdrop is None:
        return kept
    mode, k = keepdrop
    if k > n:
        raise DiceError(f"cannot {mode}{k} out of {n} dice")
    order = sorted(range(n), key=lambda i: logical_values[i])  # ascending
    if mode == "kh":
        drop_idx = order[: n - k]
    elif mode == "kl":
        drop_idx = order[k:]
    elif mode == "dh":
        drop_idx = order[n - k :]
    elif mode == "dl":
        drop_idx = order[:k]
    else:  # pragma: no cover - guarded by regex
        raise DiceError(f"unknown modifier: {mode}")
    for i in drop_idx:
        kept[i] = False
    return kept


def _term_value(term_str: str, rng: Random) -> tuple[int, list[Die]]:
    if _INT_RE.match(term_str):
        value = int(term_str)
        if value > MAX_CONSTANT:
            raise DiceError(f"constant out of bounds (0-{MAX_CONSTANT}): {term_str!r}")
        return value, []

    m = _ADV_RE.match(term_str)
    if m:
        kind, sides_s = m.group(1).lower(), m.group(2)
        sides = int(sides_s)
        if not (1 <= sides <= MAX_SIDES):
            raise DiceError(f"sides out of bounds (1-{MAX_SIDES}): d{sides}")
        chains = [_roll_logical_die(rng, sides, explode=False) for _ in range(2)]
        logical_values = [c[0].value for c in chains]
        keepdrop = ("kh", 1) if kind == "adv" else ("kl", 1)
        kept_flags = _apply_keepdrop(logical_values, keepdrop)
        dice: list[Die] = []
        total = 0
        for chain, is_kept in zip(chains, kept_flags):
            chain[0].kept = is_kept
            dice.extend(chain)
            if is_kept:
                total += chain[0].value
        return total, dice

    m = _DICE_RE.match(term_str)
    if not m:
        raise DiceError(f"cannot parse term: {term_str!r}")
    count_s, sides_s, explode_s, keepdrop_s = m.groups()
    count = int(count_s) if count_s else 1
    if not (1 <= count <= MAX_DICE_PER_TERM):
        raise DiceError(f"dice count out of bounds (1-{MAX_DICE_PER_TERM}): {term_str!r}")
    sides: Union[int, str]
    if sides_s.lower() == "f":
        sides = "F"
        if explode_s:
            raise DiceError("fate dice (dF) cannot explode")
    else:
        sides = int(sides_s)
        if not (1 <= sides <= MAX_SIDES):
            raise DiceError(f"sides out of bounds (1-{MAX_SIDES}): {term_str!r}")
    explode = bool(explode_s)
    keepdrop = _parse_keepdrop(keepdrop_s)

    chains = [_roll_logical_die(rng, sides, explode) for _ in range(count)]
    logical_values = [sum(d.value for d in c) for c in chains]
    kept_flags = _apply_keepdrop(logical_values, keepdrop)

    dice = []
    total = 0
    for chain, is_kept, lv in zip(chains, kept_flags, logical_values):
        for d in chain:
            d.kept = is_kept
        dice.extend(chain)
        if is_kept:
            total += lv
    return total, dice


def roll(expression: str, seed: Optional[int] = None) -> DiceResult:
    """Roll a dice expression. Raises DiceError on malformed/out-of-bounds input."""
    if not isinstance(expression, str) or not expression.strip():
        raise DiceError("expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise DiceError(f"expression too long (max {MAX_EXPRESSION_CHARS} characters)")
    rng: Random = Random(seed) if seed is not None else secrets.SystemRandom()

    chunks = _split_terms(expression)
    if len(chunks) > MAX_TERMS:
        raise DiceError(f"too many terms (max {MAX_TERMS})")
    asked = 0
    for chunk in chunks:
        m = _DICE_RE.match(chunk.lstrip("+-").strip())
        if m:
            asked += int(m.group(1)) if m.group(1) else 1
        elif _ADV_RE.match(chunk.lstrip("+-").strip()):
            asked += 2
    if asked > MAX_TOTAL_DICE:
        raise DiceError(f"too many dice in one roll: {asked} (max {MAX_TOTAL_DICE})")
    total = 0
    all_dice: list[Die] = []
    parts: list[str] = []
    for chunk in chunks:
        sign = 1
        body = chunk
        if body[0] in "+-":
            sign = -1 if body[0] == "-" else 1
            body = body[1:]
        body = body.strip()
        if not body:
            raise DiceError(f"cannot parse expression: {expression!r}")
        value, dice = _term_value(body, rng)
        total += sign * value
        all_dice.extend(dice)
        if len(all_dice) > MAX_ROLLED_DICE:
            raise DiceError(f"roll exploded past {MAX_ROLLED_DICE} dice; use fewer exploding dice")
        parts.append(f"{'-' if sign < 0 else '+'}{body}({value})")

    detail = " ".join(parts).lstrip("+")
    detail = f"{detail} = {total}"
    return DiceResult(expression=expression, total=total, dice=all_dice, seed=seed, detail=detail)


# ---------------------------------------------------------------------------
# Ruleset helpers
# ---------------------------------------------------------------------------

def check(dc: int, mod: int, seed: Optional[int] = None) -> dict:
    """d20 check against a difficulty class. Crit on natural 20/1."""
    result = roll("1d20", seed=seed)
    natural = result.dice[0].value
    total = natural + mod
    crit = "success" if natural == 20 else ("fail" if natural == 1 else None)
    success = total >= dc or natural == 20
    if natural == 1:
        success = False
    return {
        "natural": natural,
        "mod": mod,
        "total": total,
        "dc": dc,
        "success": success,
        "crit": crit,
        "seed": seed,
    }


def band_2d6(total: int) -> str:
    """2d6 move bands: 6- miss, 7-9 weak hit, 10+ strong hit."""
    if total >= 10:
        return "strong_hit"
    if total >= 7:
        return "weak_hit"
    return "miss"


def move(stat: int, seed: Optional[int] = None) -> dict:
    """Powered-by-the-Apocalypse 2d6 move: miss / weak hit / strong hit."""
    result = roll("2d6", seed=seed)
    total = result.total + stat
    band = band_2d6(total)
    return {
        "rolls": [d.value for d in result.dice],
        "stat": stat,
        "total": total,
        "band": band,
        "seed": seed,
    }


_PBTA_RE = re.compile(r"^2d6([+-]\d+)?$")
_D20_RE = re.compile(r"^(1?d20|adv\(d20\)|dis\(d20\))([+-]\d+)?$")


def interpret(result: DiceResult, ruleset: Optional[str]) -> dict:
    """What a roll means under the world's ruleset, when that is unambiguous.

    pbta_2d6: a plain ``2d6±N`` gets its band (miss / weak_hit /
    strong_hit). d20: a single d20 (``d20±N``, ``adv(d20)``, ``dis(d20)``)
    gets the natural value and a crit flag. Anything else: ``{}``.
    """
    expr = re.sub(r"\s+", "", result.expression.lower())
    if ruleset == "pbta_2d6" and _PBTA_RE.match(expr):
        return {"band": band_2d6(result.total)}
    if ruleset == "d20" and _D20_RE.match(expr):
        kept = [d for d in result.dice if d.kept and d.sides == 20]
        if len(kept) == 1:
            natural = kept[0].value
            return {"natural": natural, "crit": "success" if natural == 20 else ("fail" if natural == 1 else None)}
    return {}
