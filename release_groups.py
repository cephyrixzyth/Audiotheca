"""Known audio-software scene / warez release groups.

Used for vendor identification (strip group suffixes), investigation routing,
and malware heuristics (crack/keygen folders often co-locate with release groups).
"""

from __future__ import annotations

# Canonical group name -> keyword aliases seen in folder/archive names
RELEASE_GROUPS: dict[str, list[str]] = {
    "R2R": ["r2r", "revolution"],
    "TEAM R2R": ["team r2r"],
    "ARCADiA": ["arcadia", "arcadi"],
    "DECiBEL": ["decibel", "decibel audio"],
    "SYNTHiC4TE": ["synthetic4te", "synthic4te", "synthicate"],
    "V.R": ["v.r", "vr group"],
    "CHAOS": ["chaos group"],
    "HOODLUM": ["hoodlum"],
    "DYNAMiCS": ["dynamics group"],
    "ASSiGN": ["assign group"],
    "AiR": ["air group", "air music"],
    "BEAT": ["beat group"],
    "AMPLiFY": ["amplify group"],
    "P2P": ["p2p group"],
    "CHAMPiON": ["champion group"],
    "NOiR": ["noir group"],
    "ALFiSO": ["alfiso"],
    "RET": ["ret group"],
    "ZWT": ["zwt group"],
    "CE": ["ce group"],
    "TEAM BDA": ["team bda", "bda"],
    "AudioUTOPiA": ["audioutopia", "audio utopia"],
    "SPTNDC": ["sptndc"],
    "FANTASTiC": ["fantastic group"],
    "MOCHA": ["mocha group"],
    "CASHMERE": ["cashmere group"],
    "FLARE": ["flare group"],
    "RiPER": ["riper group"],
    "TCD": ["tcd group"],
    "BLAZE": ["blaze group"],
    "DiSCOVER": ["discover group"],
    "MAGNETRiXX": ["magnetrixx"],
    "H2O": ["h2o group"],
    "DAZ3D": ["daz3d group"],
    "UB": ["ub group"],
    "XFER": ["xfer group release"],
}

# Flat lookup: lowercase alias -> canonical group name
_GROUP_ALIAS_INDEX: dict[str, str] = {}
for canonical, aliases in RELEASE_GROUPS.items():
    _GROUP_ALIAS_INDEX[canonical.lower()] = canonical
    for alias in aliases:
        _GROUP_ALIAS_INDEX[alias.lower()] = canonical


def normalize_release_group(token: str) -> str | None:
    """Map a release-group token to its canonical name, or None."""
    cleaned = token.strip().strip("-_")
    if not cleaned:
        return None
    return _GROUP_ALIAS_INDEX.get(cleaned.lower())


def is_known_release_group(token: str) -> bool:
    return normalize_release_group(token) is not None


def all_group_keywords() -> set[str]:
    keys = set(_GROUP_ALIAS_INDEX.keys())
    keys.update(name.lower() for name in RELEASE_GROUPS)
    return keys
