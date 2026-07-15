EU_CODES = {
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
}

CEE_CODES = {"PL", "CZ", "SK", "HU", "RO", "BG", "SI", "HR", "EE", "LV", "LT"}
WORLD_CODES = {"WORLD", "WW"}
WORLD_EX_PL_CODES = {"WORLD_EX_PL", "WORLD-EX-PL", "WORLD_EXCLUDING_PL", "WORLD_EXCLUDING_POLAND"}
GROUP_CODES = {"EU": EU_CODES, "CEE": CEE_CODES}
KNOWN_COUNTRY_CODES = EU_CODES | CEE_CODES | {"GB", "US", "CA", "AU", "NO", "CH", "UA", "TR"}


def normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "_")


def territory_scope(codes: set[str]) -> tuple[set[str] | None, set[str]]:
    """Return included country codes and excluded codes.

    Included ``None`` means global/unbounded coverage. The helper intentionally
    keeps the universe conservative: EU/CEE are exact sets, WORLD is global, and
    unknown standalone codes behave like ordinary country/market codes.
    """
    normalized = {normalize_code(code) for code in codes if normalize_code(code)}
    if not normalized:
        return None, set()

    includes: set[str] = set()
    excludes: set[str] = set()
    global_scope = False
    for code in normalized:
        if code in WORLD_CODES:
            global_scope = True
        elif code in WORLD_EX_PL_CODES:
            global_scope = True
            excludes.add("PL")
        elif code in GROUP_CODES:
            includes.update(GROUP_CODES[code])
        else:
            includes.add(code)

    if global_scope:
        return None, excludes
    return includes, excludes


def scopes_overlap(left_codes: set[str], right_codes: set[str]) -> bool:
    left_include, left_exclude = territory_scope(left_codes)
    right_include, right_exclude = territory_scope(right_codes)

    if left_include is None and right_include is None:
        return True
    if left_include is None:
        return bool(right_include - left_exclude)
    if right_include is None:
        return bool(left_include - right_exclude)
    return bool((left_include - right_exclude) & (right_include - left_exclude))


def scope_covers(covering_codes: set[str], requested_codes: set[str]) -> bool:
    covering_include, covering_exclude = territory_scope(covering_codes)
    requested_include, requested_exclude = territory_scope(requested_codes)

    if covering_include is None:
        if requested_include is None:
            return requested_exclude.issuperset(covering_exclude)
        return not bool(requested_include & covering_exclude)
    if requested_include is None:
        return False
    effective_requested = requested_include - requested_exclude
    effective_covering = covering_include - covering_exclude
    return effective_requested.issubset(effective_covering)
