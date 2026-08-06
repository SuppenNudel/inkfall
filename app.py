from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, render_template, request
from flask_sitemap import Sitemap

from search_parser import RARITY_ORDER, parse_query

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
LORCANAJSON_URL = "https://lorcanajson.org/files/current/{lang}/allCards.json"
SUPPORTED_LANGS = ("en", "de")
PAGE_SIZE = 24

app = Flask(__name__)
app.config['SERVER_NAME'] = 'inkfall.de'
app.config['SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS'] = False
app.config['SITEMAP_URL_SCHEME'] = 'https'
ext = Sitemap(app=app)

_cache: dict[str, list[dict]] = {}
_raw_cache: dict[str, dict] = {}
_id_map_cache: dict[str, dict[int, dict]] = {}

# ── DE → EN normalization maps ────────────────────────────────────────────

_DE_COLOR: dict[str, str] = {
    "bernstein": "Amber", "amethyst": "Amethyst", "smaragd": "Emerald",
    "rubin": "Ruby", "saphir": "Sapphire", "stahl": "Steel",
}
_DE_TYPE: dict[str, str] = {
    "charakter": "Character", "aktion": "Action",
    "gegenstand": "Item", "ort": "Location",
}
_DE_RARITY: dict[str, str] = {
    "gewöhnlich": "Common", "ungewöhnlich": "Uncommon", "selten": "Rare",
    "mythisch": "Super Rare", "legendär": "Legendary", "verzaubert": "Enchanted",
    "episch": "Epic", "ikonisch": "Iconic", "speziell": "Special",
}
_DE_KW: dict[str, str] = {
    "rasant": "Rush", "behütet": "Ward", "wendig": "Evasive",
    "herausfordern": "Challenger", "impulsiv": "Reckless",
    "beschützen": "Bodyguard", "alarmiert": "Alert", "robust": "Resist",
    "singen": "Singer", "gemeinsam singen": "Sing Together",
    "gestaltwandel": "Shift", "duo-gestaltwandel": "Duo Shift",
    "flutgestaltwandel": "Floodborn Shift", "kartoffel-gestaltwandel": "Potato Shift",
    "kombo-gestaltwandel": "Combo Shift", "madrigal-gestaltwandel": "Madrigal Shift",
    "temporärer gestaltwandel": "Temporary Shift",
    "temporärer roter-panda-gestaltwandel": "Temporary Red Panda Shift",
    "universal-gestaltwandel": "Universal Shift", "welpen-gestaltwandel": "Puppy Shift",
    "stärken": "Boost", "unterstützen": "Support",
    "verschwinden": "Vanish", "verteidigen": "Defend",
}


def _normalize_de_color(de_color: str) -> str:
    """Translate a DE color string (may be hyphenated dual-ink) to EN."""
    parts = de_color.split("-")
    return "-".join(_DE_COLOR.get(p.lower(), p) for p in parts)


def _annotate_de_cards(de_cards: list[dict]) -> None:
    """Add _color/_type/_rarity/_keywords/_subtypes/_story EN shadow fields to DE cards."""
    en_by_id = _get_id_map("en")  # ensures EN is loaded; safe, no circular dep
    for c in de_cards:
        c_en = en_by_id.get(c["id"])
        c["_color"] = _normalize_de_color(c.get("color") or "")
        c["_type"] = _DE_TYPE.get((c.get("type") or "").lower(), c.get("type", ""))
        c["_rarity"] = _DE_RARITY.get((c.get("rarity") or "").lower(), c.get("rarity", ""))
        c["_keywords"] = [_DE_KW.get(kw.lower(), kw) for kw in (c.get("keywordAbilities") or [])]
        if c_en:
            c["_subtypes"] = c_en.get("subtypes") or []
            c["_subtypesText"] = c_en.get("subtypesText") or ""
            c["_story"] = c_en.get("story") or ""
        else:
            c["_subtypes"] = c.get("subtypes") or []
            c["_subtypesText"] = c.get("subtypesText") or ""
            c["_story"] = c.get("story") or ""


def _annotate_set_names(cards: list[dict], sets_meta: dict) -> None:
    """Add normalized set name shadow field used for set-name search."""
    for c in cards:
        set_code = c.get("setCode", "")
        c["_setName"] = sets_meta.get(set_code, {}).get("name", "")


def _data_path(lang: str) -> Path:
    return DATA_DIR / f"allCards_{lang}.json"


def _fetch_and_save(lang: str) -> dict:
    url = LORCANAJSON_URL.format(lang=lang)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _data_path(lang).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _load(lang: str) -> dict:
    if lang not in _raw_cache:
        path = _data_path(lang)
        if path.exists() and path.stat().st_size > 0:
            try:
                _raw_cache[lang] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                _raw_cache[lang] = _fetch_and_save(lang)
        else:
            _raw_cache[lang] = _fetch_and_save(lang)
        _cache[lang] = _raw_cache[lang]["cards"]
        _annotate_set_names(_cache[lang], _raw_cache[lang].get("sets", {}))
        if lang == "de":
            _annotate_de_cards(_cache[lang])
    return _raw_cache[lang]


def get_cards(lang: str) -> list[dict]:
    _load(lang)
    return _cache[lang]


def _get_id_map(lang: str) -> dict[int, dict]:
    if lang not in _id_map_cache:
        _id_map_cache[lang] = {c["id"]: c for c in get_cards(lang)}
    return _id_map_cache[lang]


def _get_card_by_id(card_id: int, lang: str) -> dict | None:
    return _get_id_map(lang).get(card_id)


def _get_card_versions(card_id: int, lang: str) -> list[dict]:
    """Return all related cards (all versions/printings) sorted for display."""
    by_id = _get_id_map(lang)

    # Walk up to the canonical root (follow baseId, then reprintOfId)
    root_id = card_id
    for _ in range(10):  # cycle guard
        c = by_id.get(root_id)
        if not c:
            break
        if c.get("baseId"):
            root_id = c["baseId"]
        elif c.get("reprintOfId"):
            root_id = c["reprintOfId"]
        else:
            break

    root = by_id.get(root_id)
    if not root:
        return []

    # Collect all related IDs from the root
    collected: dict[int, str] = {}  # id -> version_type

    def _add(cid: int | None, vtype: str) -> None:
        if cid is not None and cid not in collected:
            collected[cid] = vtype

    _add(root_id, "base")
    _add(root.get("enchantedId"), "enchanted")
    _add(root.get("epicId"), "epic")
    _add(root.get("iconicId"), "iconic")
    for pid in (root.get("promoIds") or []):
        _add(pid, "promo")
    for vid in (root.get("variantIds") or []):
        _add(vid, "variant")
    for rid in (root.get("reprintedAsIds") or []):
        _add(rid, "reprint")
        # Also include premium versions of reprints
        reprint = by_id.get(rid)
        if reprint:
            _add(reprint.get("enchantedId"), "enchanted")
            _add(reprint.get("epicId"), "epic")
            _add(reprint.get("iconicId"), "iconic")

    # Build version list
    raw = _load(lang)
    sets_meta = raw.get("sets", {})

    versions = []
    for vid, vtype in collected.items():
        c = by_id.get(vid)
        if not c:
            continue
        images = c.get("images", {})
        set_code = c.get("setCode", "")
        set_name = sets_meta.get(set_code, {}).get("name", f"Set {set_code}")
        rarity = c.get("rarity", "")

        label_parts = []
        if vtype == "base":
            label_parts.append(set_name)
        elif vtype == "reprint":
            label_parts.append(f"{set_name} (Reprint)")
        elif vtype == "variant":
            letter = (c.get("variant") or "").upper()
            label_parts.append(f"Variant {letter}" if letter else "Variant")
        elif vtype == "promo":
            label_parts.append(f"Promo · {c.get('promoGrouping') or set_code}")
        else:
            label_parts.append(rarity)  # Enchanted / Epic / Iconic
            label_parts.append(f"({set_name})")

        versions.append({
            "id": vid,
            "label": " ".join(label_parts),
            "sublabel": rarity,
            "rarity": rarity,
            "type": vtype,
            "setCode": set_code,
            "setName": set_name,
            "number": c.get("number"),
            "fullIdentifier": c.get("fullIdentifier", ""),
            "thumbnail": images.get("thumbnail", ""),
            "isCurrent": vid == card_id,
        })

    # Sort: base first, then reprints by set, then variants, then enchanted/epic/promo
    type_order = {"base": 0, "reprint": 1, "variant": 2, "promo": 3, "enchanted": 4, "epic": 5, "iconic": 6}

    def _sort_key(v: dict):
        try:
            set_num = int(v["setCode"])
        except (ValueError, TypeError):
            set_num = 999
        return (type_order.get(v["type"], 9), set_num)

    versions.sort(key=_sort_key)
    return versions


def _card_summary(c: dict) -> dict:
    images = c.get("images", {})
    return {
        "id": c["id"],
        "fullName": c.get("fullName", c.get("name", "")),
        "name": c.get("name", ""),
        "version": c.get("version", ""),
        "color": c.get("color", ""),
        # EN color name for CSS classes (strip dual-ink suffix)
        "colorClass": (c.get("_color") or c.get("color", "")).split("-")[0].strip().lower(),
        "type": c.get("type", ""),
        "rarity": c.get("rarity", ""),
        "cost": c.get("cost"),
        "lore": c.get("lore"),
        "strength": c.get("strength"),
        "willpower": c.get("willpower"),
        "inkwell": c.get("inkwell", False),
        "setCode": c.get("setCode", ""),
        "story": c.get("story", ""),
        "thumbnail": images.get("thumbnail", ""),
        "keywordAbilities": c.get("keywordAbilities", []),
        "subtypesText": c.get("subtypesText", ""),
    }


def _card_detail(c: dict) -> dict:
    d = _card_summary(c)
    images = c.get("images", {})
    d.update({
        "fullImage": images.get("full", ""),
        "fullText": c.get("fullText", ""),
        "flavorText": c.get("flavorText", ""),
        "abilities": c.get("abilities", []),
        "effects": c.get("effects", []),
        "artistsText": c.get("artistsText", ""),
        "moveCost": c.get("moveCost"),
        "fullIdentifier": c.get("fullIdentifier", ""),
        "allowedInFormats": c.get("allowedInFormats", {}),
        "cardmarketUrl": (c.get("externalLinks") or {}).get("cardmarketUrl", ""),
        "colorClass": (c.get("_color") or c.get("color", "")).split("-")[0].strip().lower(),
        # EN story name — used for search links regardless of display language
        "storyEn": c.get("_story") or c.get("story", ""),
    })
    return d


@ext.register_generator
def sitemap_urls():
    """Register all public pages for Flask-Sitemap."""
    yield "index", {}
    yield "advanced", {}
    yield "browse", {}

    try:
        cards = get_cards("en")
    except Exception:
        return

    for card in cards:
        if card.get("baseId") or card.get("reprintOfId"):
            continue
        if card.get("variant") and card.get("variant") != "a":
            continue
        yield "card_page", {"card_id": card["id"]}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/card/<int:card_id>")
def card_page(card_id: int):
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    card = _get_card_by_id(card_id, lang)
    if card is None:
        abort(404)
    raw = _load(lang)
    set_name = raw.get("sets", {}).get(card.get("setCode", ""), {}).get("name", "")
    versions = _get_card_versions(card_id, lang)
    return render_template(
        "card.html",
        card=_card_detail(card),
        versions=versions,
        lang=lang,
        set_name=set_name,
        card_id=card_id,
    )


@app.route("/api/meta")
def api_meta():
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    raw = _load(lang)
    cards = raw["cards"]

    colors = sorted({c.get("color", "") for c in cards if c.get("color")})
    types = sorted({c.get("type", "") for c in cards if c.get("type")})
    rarities_present = {c.get("rarity", "") for c in cards if c.get("rarity")}
    rarities = [r for r in RARITY_ORDER if r in rarities_present]
    rarities += sorted(rarities_present - set(RARITY_ORDER))

    def _set_sort_key(code: str):
        try:
            return (0, int(code))
        except ValueError:
            return (1, code)

    sets_sorted = sorted(
        ((code, info.get("name", code)) for code, info in raw.get("sets", {}).items()),
        key=lambda x: _set_sort_key(x[0]),
    )

    return jsonify({"colors": colors, "types": types, "rarities": rarities, "sets": sets_sorted})


@app.route("/api/cards")
def api_cards():
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"

    q = request.args.get("q", "").strip()
    unique = request.args.get("unique", "cards")  # "cards" or "prints"
    sort_by = request.args.get("sort", "name")
    sort_dir = request.args.get("sort_dir", "asc")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    cards = get_cards(lang)

    parse_error = None
    warnings: list[str] = []
    if q:
        try:
            predicate, warnings = parse_query(q)
            result = [c for c in cards if predicate(c)]
        except Exception as exc:
            parse_error = str(exc)
            result = []
    else:
        result = list(cards)

    # "Cards" view: one entry per unique card — hide premium alts, non-first variants, reprints
    if unique == "cards":
        result = [
            c for c in result
            if not c.get("baseId")
            and not c.get("reprintOfId")
            and (not c.get("variant") or c.get("variant") == "a")
        ]

    _sort_keys = {
        "name":      lambda c: (c.get("simpleName") or ""),
        "cost":      lambda c: (c.get("cost") is None, c.get("cost") or 0),
        "lore":      lambda c: (c.get("lore") is None, c.get("lore") or 0),
        "strength":  lambda c: (c.get("strength") is None, c.get("strength") or 0),
        "willpower": lambda c: (c.get("willpower") is None, c.get("willpower") or 0),
        "rarity":    lambda c: (
            RARITY_ORDER.index(c["rarity"]) if c.get("rarity") in RARITY_ORDER else 99
        ),
    }
    key_fn = _sort_keys.get(sort_by, _sort_keys["name"])
    result = sorted(result, key=key_fn, reverse=(sort_dir == "desc"))

    total = len(result)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE

    resp = {
        "cards": [_card_summary(c) for c in result[start: start + PAGE_SIZE]],
        "total": total,
        "page": page,
        "pages": total_pages,
        "per_page": PAGE_SIZE,
    }
    if parse_error:
        resp["error"] = parse_error
    if warnings:
        resp["warnings"] = warnings
    return jsonify(resp)


@app.route("/api/card/<int:card_id>")
def api_card(card_id: int):
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    card = _get_card_by_id(card_id, lang)
    if card is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(card)


@app.route("/api/refresh")
def api_refresh():
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        return jsonify({"error": "unsupported language"}), 400
    try:
        data = _fetch_and_save(lang)
        _raw_cache[lang] = data
        _cache[lang] = data["cards"]
        _id_map_cache.pop(lang, None)
        if lang == "de":
            _annotate_de_cards(_cache[lang])
        return jsonify({"ok": True, "count": len(data["cards"])})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/advanced")
def advanced():
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    raw = _load(lang)

    def _set_sort_key(code):
        try:
            return (0, int(code))
        except ValueError:
            return (1, code)

    sets_sorted = sorted(
        ((code, info.get("name", code)) for code, info in raw.get("sets", {}).items()),
        key=lambda x: _set_sort_key(x[0]),
    )
    return render_template("advanced.html", lang=lang, sets=sets_sorted)


@app.route("/browse")
def browse():
    lang = request.args.get("lang", "en")
    if lang not in SUPPORTED_LANGS:
        lang = "en"

    from collections import Counter

    # Stories: use current lang's story names for display; EN names used in queries via _story
    lang_cards = get_cards(lang)
    story_counts = Counter(c.get("story", "").strip() for c in lang_cards if c.get("story"))
    stories = sorted(story_counts.items())

    # Sets: display localized set names and link by set code
    raw = _load(lang)
    sets_meta = raw.get("sets", {})
    set_counts: dict[str, int] = {}
    for c in lang_cards:
        set_code = c.get("setCode", "")
        if set_code:
            set_counts[set_code] = set_counts.get(set_code, 0) + 1

    def _set_sort_key(code: str):
        try:
            return (0, int(code))
        except ValueError:
            return (1, code)

    sets = [
        (code, sets_meta.get(code, {}).get("name", f"Set {code}"), count)
        for code, count in set_counts.items()
    ]
    sets.sort(key=lambda row: _set_sort_key(row[0]))

    # Character names: use current lang's `name` field from Character cards
    # `type` and `name` fields of Character cards may differ in DE, use _type/_name awareness
    char_counts: dict[str, int] = {}
    for c in lang_cards:
        card_type = c.get("_type") or c.get("type", "")
        if card_type == "Character" and c.get("name"):
            char_counts[c["name"]] = char_counts.get(c["name"], 0) + 1
    chars = sorted(char_counts.items())

    # Artists: split multi-artist cards and count each artist occurrence
    artist_counts: dict[str, int] = {}
    for c in lang_cards:
        artists_text = (c.get("artistsText") or "").strip()
        if not artists_text:
            continue
        for artist in [a.strip() for a in artists_text.split(" • ") if a.strip()]:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
    artists = sorted(artist_counts.items())

    return render_template(
        "browse.html",
        lang=lang,
        stories=stories,
        sets=sets,
        chars=chars,
        artists=artists,
    )


@app.route("/impressum")
def impressum():
    lang = request.args.get("lang", "de")
    if lang not in SUPPORTED_LANGS:
        lang = "de"
    return render_template("legal.html", page="impressum", page_title="Impressum", lang=lang)


@app.route("/datenschutz")
def datenschutz():
    lang = request.args.get("lang", "de")
    if lang not in SUPPORTED_LANGS:
        lang = "de"
    return render_template("legal.html", page="datenschutz", page_title="Datenschutzerklärung", lang=lang)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8085))
    app.run(host="0.0.0.0", port=port)
