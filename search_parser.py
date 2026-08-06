"""Scryfall-style query parser for Lorcana cards."""
from __future__ import annotations

import re
import threading
from typing import Callable

_tl = threading.local()


def _warn(msg: str) -> None:
    if hasattr(_tl, "warnings"):
        _tl.warnings.append(msg)

Predicate = Callable[[dict], bool]

# ── Lorcana constants ──────────────────────────────────────────────────────

_COLOR_MAP: dict[str, str] = {
    # Full names
    "amber": "Amber", "amethyst": "Amethyst", "emerald": "Emerald",
    "ruby": "Ruby", "sapphire": "Sapphire", "steel": "Steel",
    # Short codes (a conflicts with artist so skip it)
    "am": "Amethyst", "em": "Emerald", "ru": "Ruby", "sa": "Sapphire",
    # Letter shortcuts (Scryfall-style mnemonic)
    "y": "Amber",    # Yellow
    "p": "Amethyst", # Purple
    "g": "Emerald",  # Green
    "r": "Ruby",     # Red
    "b": "Sapphire", # Blue
    "s": "Steel",    # Silver
}

_RARITY_MAP: dict[str, str] = {
    "c": "Common", "common": "Common",
    "u": "Uncommon", "uncommon": "Uncommon",
    "r": "Rare", "rare": "Rare",
    "sr": "Super Rare", "superrare": "Super Rare", "super": "Super Rare",
    "l": "Legendary", "legendary": "Legendary",
    "e": "Enchanted", "enchanted": "Enchanted",
    "ep": "Epic", "epic": "Epic",
    "ic": "Iconic", "iconic": "Iconic",
    "sp": "Special", "special": "Special", "promo": "Special",
}

RARITY_ORDER: list[str] = [
    "Common", "Uncommon", "Rare", "Super Rare",
    "Legendary", "Enchanted", "Epic", "Iconic", "Special",
]

_CLAUSE_RE = re.compile(r"^(-?)([a-zA-Z]+)([:<>=!]+)(.+)$")


def _resolve_color(val: str) -> str:
    return _COLOR_MAP.get(val.lower(), val.capitalize())


def _resolve_rarity(val: str) -> str:
    key = re.sub(r"[\s\-_]", "", val.lower())
    return _RARITY_MAP.get(key, val.title())


def _numeric_cmp(a: int | None, b: int, op: str) -> bool:
    if a is None:
        return False
    return {
        ":": a == b, "=": a == b, "!=": a != b,
        ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b,
    }.get(op, False)


def _rarity_cmp(rarity: str, target_rarity: str, op: str) -> bool:
    try:
        return _numeric_cmp(RARITY_ORDER.index(rarity), RARITY_ORDER.index(target_rarity), op)
    except ValueError:
        return False


# ── tokenizer ───────────────────────────────────────────────────────────────

def _tokenize(query: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(query)
    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
        elif ch in "()":
            tokens.append(ch)
            i += 1
        elif ch == '"':
            j = query.find('"', i + 1)
            if j == -1:
                tokens.append(query[i + 1 :])
                break
            tokens.append(query[i : j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not query[j].isspace() and query[j] not in "()":
                if query[j] == '"':
                    end = query.find('"', j + 1)
                    j = (end + 1) if end != -1 else n
                    break
                j += 1
            tokens.append(query[i:j])
            i = j
    return [t for t in tokens if t.strip()]


# ── clause builders ──────────────────────────────────────────────────────────

def _is_predicate(v: str) -> Predicate:
    mapping: dict[str, Predicate] = {
        "inkable": lambda c: bool(c.get("inkwell")),
        "inkwell": lambda c: bool(c.get("inkwell")),
        "notinkable": lambda c: not c.get("inkwell", False),
        "uninkable": lambda c: not c.get("inkwell", False),
        "song": lambda c: "Song" in (c.get("_subtypes") or c.get("subtypes") or []),
        "banned": lambda c: any(
            not f.get("allowed", True)
            for f in (c.get("allowedInFormats") or {}).values()
        ),
        "legal": lambda c: any(
            f.get("allowed", False)
            for f in (c.get("allowedInFormats") or {}).values()
        ),
        "character": lambda c: c.get("type") == "Character",
        "action": lambda c: c.get("type") == "Action",
        "item": lambda c: c.get("type") == "Item",
        "location": lambda c: c.get("type") == "Location",
        # vanilla = no rules text at all
        "vanilla": lambda c: not (c.get("fullText") or "").strip(),
        # french-vanilla = only keyword abilities, no named/activated/triggered/static abilities
        "frenchvanilla": lambda c: (
            bool(c.get("_keywords") or c.get("keywordAbilities"))
            and all(a.get("type") == "keyword" for a in (c.get("abilities") or []))
            and not (c.get("effects") or [])
        ),
        "french-vanilla": lambda c: (
            bool(c.get("_keywords") or c.get("keywordAbilities"))
            and all(a.get("type") == "keyword" for a in (c.get("abilities") or []))
            and not (c.get("effects") or [])
        ),
    }
    result = mapping.get(v)
    if result is None:
        _warn(f"Unknown is: value \u2018{v}\u2019")
        return lambda c: False
    return result


def _build_clause(keyword: str, op: str, raw_value: str) -> Predicate:
    val = raw_value.strip('"')
    vl = val.lower()
    kw = keyword.lower()

    if kw in ("c", "color", "ink"):
        color = _resolve_color(vl)
        _KNOWN_COLORS = set(_COLOR_MAP.values())
        if color not in _KNOWN_COLORS:
            _warn(f"Unknown color \u2018{val}\u2019 \u2014 try: amber, amethyst, emerald, ruby, sapphire, steel (or a/p/g/r/b/s)")
        return lambda c, col=color: col.lower() in (c.get("_color") or c.get("color", "")).lower()

    if kw in ("t", "type"):
        return lambda c, tv=vl: (
            tv in (c.get("_type") or c.get("type", "")).lower()
            or tv in (c.get("_subtypesText") or c.get("subtypesText") or "").lower()
        )

    if kw in ("r", "rarity"):
        target = _resolve_rarity(val)
        if target not in RARITY_ORDER:
            _warn(f"Unknown rarity \u2018{val}\u2019 \u2014 try: c, u, r, sr, l, e, ep, ic, sp")
        if op in (":", "="):
            return lambda c, t=target: (c.get("_rarity") or c.get("rarity", "")).lower() == t.lower()
        return lambda c, t=target, o=op: _rarity_cmp(c.get("_rarity") or c.get("rarity", ""), t, o)

    if kw in ("s", "e", "set", "edition", "ed"):
        return lambda c, sv=vl: (
            c.get("setCode", "").lower() == sv
            or sv in (c.get("_setName") or "").lower()
        )

    if kw in ("o", "oracle", "text"):
        return lambda c, tv=vl: tv in (c.get("fullText") or "").lower()

    if kw in ("kw", "keyword"):
        return lambda c, kv=vl: any(
            kv in k.lower() for k in (c.get("_keywords") or c.get("keywordAbilities") or [])
        )

    if kw in ("a", "artist"):
        return lambda c, av=vl: av in (c.get("artistsText") or "").lower()

    if kw in ("ft", "flavor"):
        return lambda c, fv=vl: fv in (c.get("flavorText") or "").lower()

    if kw in ("story", "franchise"):
        # check normalized EN field (_story) AND raw localized field so both langs work
        return lambda c, sv=vl: (
            sv in (c.get("_story") or "").lower()
            or sv in (c.get("story") or "").lower()
        )

    if kw in ("n", "name"):
        return lambda c, nv=vl: (
            nv in (c.get("simpleName") or "").lower()
            or nv in (c.get("fullName") or "").lower()
        )

    if kw in ("char", "character"):
        # exact match on the base character name (without version subtitle)
        return lambda c, nv=vl: (c.get("name") or "").lower() == nv

    if kw in ("cost", "mv", "manavalue"):
        try:
            num = int(val)
            return lambda c, n=num, o=op: _numeric_cmp(c.get("cost"), n, o)
        except ValueError:
            _warn(f"Expected a number for \u2018{kw}\u2019, got \u2018{val}\u2019")
            return lambda c: False

    if kw in ("str", "strength", "pow", "power"):
        try:
            num = int(val)
            return lambda c, n=num, o=op: _numeric_cmp(c.get("strength"), n, o)
        except ValueError:
            _warn(f"Expected a number for \u2018{kw}\u2019, got \u2018{val}\u2019")
            return lambda c: False

    if kw in ("wp", "willpower", "tou", "toughness"):
        try:
            num = int(val)
            return lambda c, n=num, o=op: _numeric_cmp(c.get("willpower"), n, o)
        except ValueError:
            _warn(f"Expected a number for \u2018{kw}\u2019, got \u2018{val}\u2019")
            return lambda c: False

    if kw == "lore":
        try:
            num = int(val)
            return lambda c, n=num, o=op: _numeric_cmp(c.get("lore"), n, o)
        except ValueError:
            _warn(f"Expected a number for 'lore', got '{val}'")
            return lambda c: False

    if kw == "is":
        return _is_predicate(vl)

    if kw == "not":
        p = _is_predicate(vl)
        return lambda c, p=p: not p(c)



    # Unknown keyword → treat whole token as name search fallback
    full = f"{keyword}:{val}".lower()
    return lambda c, f=full: f in (c.get("simpleName") or "").lower()


# ── recursive descent parser ─────────────────────────────────────────────────

def _parse_expr(tokens: list[str], pos: int) -> tuple[Predicate, int]:
    """Parse tokens[pos:] into a predicate, stopping at ')' or end."""
    parts: list[tuple[bool, Predicate]] = []
    next_or = False

    while pos < len(tokens) and tokens[pos] != ")":
        if tokens[pos].upper() == "OR":
            next_or = True
            pos += 1
            continue
        pred, pos = _parse_term(tokens, pos)
        parts.append((next_or, pred))
        next_or = False

    return _combine(parts), pos


def _parse_term(tokens: list[str], pos: int) -> tuple[Predicate, int]:
    tok = tokens[pos]

    negate = False
    if tok.startswith("-") and len(tok) > 1:
        negate = True
        tok = tok[1:]

    if tok == "(":
        pred, pos = _parse_expr(tokens, pos + 1)
        if pos < len(tokens) and tokens[pos] == ")":
            pos += 1
    else:
        pred, pos = _parse_atom(tok, pos + 1)

    if negate:
        p = pred
        return lambda c, p=p: not p(c), pos
    return pred, pos


def _parse_atom(tok: str, pos: int) -> tuple[Predicate, int]:
    # Quoted bare phrase → name search
    if tok.startswith('"') and tok.endswith('"'):
        phrase = tok[1:-1].lower()
        return lambda c, ph=phrase: ph in (c.get("simpleName") or "").lower(), pos

    # Exact name match
    if tok.startswith("!"):
        exact = tok[1:].strip('"').lower()
        return (
            lambda c, e=exact: (c.get("simpleName") or "").lower() == e
            or (c.get("fullName") or "").lower() == e,
            pos,
        )

    # Keyword clause
    m = _CLAUSE_RE.match(tok)
    if m:
        neg, keyword, op, value = m.groups()
        pred = _build_clause(keyword, op, value)
        if neg:
            p = pred
            return lambda c, p=p: not p(c), pos
        return pred, pos

    # Bare word → name contains
    vl = tok.lower()
    return lambda c, v=vl: v in (c.get("simpleName") or "").lower(), pos


def _combine(parts: list[tuple[bool, Predicate]]) -> Predicate:
    if not parts:
        return lambda c: True

    # Split into OR groups: each new group starts when is_or=True
    groups: list[list[Predicate]] = [[]]
    for is_or, pred in parts:
        if is_or:
            groups.append([])
        groups[-1].append(pred)

    and_preds = [
        (lambda c, ps=g: all(p(c) for p in ps)) if len(g) > 1 else g[0]
        for g in groups
    ]

    if len(and_preds) == 1:
        return and_preds[0]
    gps = and_preds
    return lambda c, gps=gps: any(g(c) for g in gps)


def parse_query(query: str) -> tuple[Predicate, list[str]]:
    """Parse a Scryfall-style Lorcana query string into (predicate, warnings)."""
    _tl.warnings = []
    query = query.strip()
    if not query:
        return lambda c: True, []
    tokens = _tokenize(query)
    pred, _ = _parse_expr(tokens, 0)
    return pred, list(_tl.warnings)
