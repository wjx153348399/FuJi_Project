from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from zk_impedance_upload.scanner import CandidateFile


REGION_ALIASES = {
    "AFX": "AFX",
    "JXN": "JXN",
    "LXD": "LXD",
    "OUTER": "OUTER",
    "ZGL": "ZGL",
    "LXD & AFX": "LXD_AFX",
    "LXD & AFX & JXN": "LXD_AFX_JXN",
}



@dataclass(frozen=True)
class ParsedFile:
    path: Path
    filename: str
    directory: Path
    size: int
    modified_at: str
    flow: str
    filePath: str
    region: str
    normalized_name: str
    business_key: str
    fallback_key: str
    dedupe_key: str


def parse_candidate(candidate: CandidateFile) -> ParsedFile:
    region = identify_region(candidate.path)
    normalized_name = normalize_filename(candidate.path.name)
    modified_at = candidate.modified_at.strftime("%Y-%m-%d %H:%M:%S")
    flow_key = candidate.flow.strip() or candidate.filePath or str(candidate.path)
    fallback_key = f"FALLBACK|{flow_key}|{region}|{normalized_name}|{candidate.size}|{modified_at}"

    return ParsedFile(
        path=candidate.path,
        filename=candidate.path.name,
        directory=candidate.path.parent,
        size=candidate.size,
        modified_at=modified_at,
        flow=candidate.flow,
        filePath=candidate.filePath,
        region=region,
        normalized_name=normalized_name,
        business_key="",
        fallback_key=fallback_key,
        dedupe_key=fallback_key,
    )


def identify_region(path: Path) -> str:
    parts = [part.strip() for part in path.parts]
    for part in reversed(parts[:-1]):
        if part in REGION_ALIASES:
            return REGION_ALIASES[part]
    return "UNKNOWN"


def normalize_filename(filename: str) -> str:
    name = Path(filename).stem.strip()
    name = name.replace("（", "(").replace("）", ")")
    name = re.sub(r"\s+", "-", name)
    name = name.replace("_", "-")
    name = re.sub(r"-+", "-", name)
    name = re.sub(r"\s*\(\d+\)$", "", name)
    name = name.strip("-")
    return name.upper()
