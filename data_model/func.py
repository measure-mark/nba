from leagues.links import LinkScheme

# The NBA scheme, kept as a module-level default so the long-standing
# bs_filename_to_* helpers keep working for callers that predate multi-league support.
# New code should go through league.links instead.
_NBA_LINKS = LinkScheme()


def bs_filename_to_date(x: str) -> str:
    return _NBA_LINKS.parse_boxscore_filename(x)[0]


def bs_filename_to_hometeam(x: str) -> str:
    return _NBA_LINKS.parse_boxscore_filename(x)[1]
