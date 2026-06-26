from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from zk_impedance_upload.parser import ParsedFile


class HashProvider(Protocol):
    def get(self, path) -> str:
        ...


@dataclass(frozen=True)
class BatchSkippedFile:
    parsed_file: ParsedFile
    file_hash: str
    action: str
    reason: str


@dataclass(frozen=True)
class BatchDedupeResult:
    selected: list[ParsedFile]
    skipped: list[BatchSkippedFile]


def dedupe_batch(parsed_files: list[ParsedFile], hash_cache: HashProvider) -> BatchDedupeResult:
    light_groups: dict[tuple[str, str, int, str], list[ParsedFile]] = {}
    for parsed_file in parsed_files:
        light_key = (
            parsed_file.region,
            parsed_file.normalized_name,
            parsed_file.size,
            parsed_file.modified_at,
        )
        light_groups.setdefault(light_key, []).append(parsed_file)

    selected: list[ParsedFile] = []
    skipped: list[BatchSkippedFile] = []

    for group in light_groups.values():
        if len(group) == 1:
            selected.append(group[0])
            continue

        hash_groups: dict[str, list[ParsedFile]] = {}
        for parsed_file in group:
            file_hash = hash_cache.get(parsed_file.path)
            hash_groups.setdefault(file_hash, []).append(parsed_file)

        for file_hash, hash_group in hash_groups.items():
            keep_file = hash_group[0]
            selected.append(keep_file)
            for duplicate in hash_group[1:]:
                skipped.append(
                    BatchSkippedFile(
                        parsed_file=duplicate,
                        file_hash=file_hash,
                        action="batch_duplicate_skipped",
                        reason="同一批次内重复文件",
                    )
                )

    return BatchDedupeResult(selected=selected, skipped=skipped)
