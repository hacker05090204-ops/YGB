from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class CleanCandidate:
    relative_path: str
    rule: str
    is_dir: bool
    age_days: float | None = None

    @property
    def entry_type(self) -> str:
        return "DIR" if self.is_dir else "FILE"

    def describe(self) -> str:
        age_note = ""
        if self.age_days is not None:
            age_note = f" | age_days={self.age_days:.2f}"
        return f"{self.entry_type} {self.relative_path} | rule={self.rule}{age_note}"


@dataclass
class CleanResult:
    dry_run: bool
    scanned_paths: int = 0
    protected_paths: int = 0
    candidates: list[CleanCandidate] = field(default_factory=list)
    deleted_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def matched_paths(self) -> int:
        return len(self.candidates)

    @property
    def directory_candidates(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.is_dir)

    @property
    def file_candidates(self) -> int:
        return sum(1 for candidate in self.candidates if not candidate.is_dir)

    @property
    def eligible_log_candidates(self) -> int:
        return sum(1 for candidate in self.candidates if candidate.rule.endswith(".log"))


class RepoClean:
    REMOVE_PATTERNS = (
        "**/__pycache__/",
        "*.pyc",
        "*.pyo",
        ".pytest_cache/",
        ".ruff_cache/",
        ".tmp_agent_reports/",
        "backend-test-results-artifact/",
        "archive_bundle/",
        ".tmp_hdd_drive/**/*.lock",
        ".tmp_hdd_drive/**/*.meta",
        ".tmp_hdd_drive/**/*.log",
        "*.log",
        "*.safetensors.tmp",
        "*.descriptions.jsonl.tmp",
    )

    KEEP_ALWAYS = (
        "secure_data",
        "checkpoints",
        "backend",
        "impl_v1",
        "native",
        "governance",
        "scripts",
        "tests",
        "pyproject.toml",
        "setup.sh",
    )

    LOG_RETENTION_DAYS = 7
    TEMP_RETENTION_DAYS = 1
    INTERNAL_SKIP = {".git"}
    OUT_OF_SCOPE_ROOTS = {"frontend"}

    def __init__(self, repo_root: Path, dry_run: bool = True) -> None:
        self.repo_root = repo_root.resolve()
        self.dry_run = dry_run
        self.clean_log_path = self.repo_root / "scripts" / "clean_log.txt"

    def run(self) -> int:
        before = self.scan()
        self._print_summary("Before cleanup", before, include_candidates=True)

        if self.dry_run:
            print("Dry-run mode active. No files or directories were deleted.")
            self._print_summary("After cleanup (dry-run)", before, include_candidates=False)
            return 1 if before.errors else 0

        self._execute_candidates(before)
        self._print_execution_result(before)

        after = self.scan()
        self._print_summary("After cleanup", after, include_candidates=bool(after.candidates))
        return 1 if before.errors or after.errors else 0

    def scan(self) -> CleanResult:
        result = CleanResult(dry_run=self.dry_run)
        self._scan_dir(self.repo_root, result)
        return result

    def _scan_dir(self, current_dir: Path, result: CleanResult) -> None:
        try:
            entries = sorted(
                current_dir.iterdir(),
                key=lambda item: (not self._is_real_directory(item), item.as_posix().lower()),
            )
        except OSError as exc:
            relative_dir = current_dir.relative_to(self.repo_root).as_posix() if current_dir != self.repo_root else "."
            result.errors.append(f"Failed to read directory {relative_dir}: {exc}")
            return

        for entry in entries:
            relative_path = entry.relative_to(self.repo_root).as_posix()

            if self._is_internal_skip(relative_path):
                continue

            result.scanned_paths += 1

            if self._is_protected(relative_path):
                result.protected_paths += 1
                continue

            if self._is_real_directory(entry):
                directory_rule = self._match_directory_rule(relative_path, entry.name)
                if directory_rule is not None:
                    result.candidates.append(
                        CleanCandidate(
                            relative_path=relative_path,
                            rule=directory_rule,
                            is_dir=True,
                        )
                    )
                    continue
                self._scan_dir(entry, result)
                continue

            file_candidate = self._match_file_rule(entry, relative_path, result)
            if file_candidate is not None:
                result.candidates.append(file_candidate)

    def _match_directory_rule(self, relative_path: str, name: str) -> str | None:
        if name == "__pycache__":
            return self.REMOVE_PATTERNS[0]

        directory_rules = {
            ".pytest_cache": self.REMOVE_PATTERNS[3],
            ".ruff_cache": self.REMOVE_PATTERNS[4],
            ".tmp_agent_reports": self.REMOVE_PATTERNS[5],
            "backend-test-results-artifact": self.REMOVE_PATTERNS[6],
            "archive_bundle": self.REMOVE_PATTERNS[7],
        }
        return directory_rules.get(relative_path)

    def _match_file_rule(
        self,
        entry: Path,
        relative_path: str,
        result: CleanResult,
    ) -> CleanCandidate | None:
        suffix = entry.suffix.lower()
        entry_name = entry.name.lower()

        if suffix == ".pyc":
            return CleanCandidate(relative_path=relative_path, rule=self.REMOVE_PATTERNS[1], is_dir=False)

        if suffix == ".pyo":
            return CleanCandidate(relative_path=relative_path, rule=self.REMOVE_PATTERNS[2], is_dir=False)

        if relative_path.startswith(".tmp_hdd_drive/") and suffix == ".lock":
            return CleanCandidate(relative_path=relative_path, rule=self.REMOVE_PATTERNS[8], is_dir=False)

        if relative_path.startswith(".tmp_hdd_drive/") and suffix == ".meta":
            return CleanCandidate(relative_path=relative_path, rule=self.REMOVE_PATTERNS[9], is_dir=False)

        if suffix == ".log":
            age_days = self._get_age_days(entry, result)
            if age_days is None or age_days < self.LOG_RETENTION_DAYS:
                return None

            rule = self.REMOVE_PATTERNS[10] if relative_path.startswith(".tmp_hdd_drive/") else self.REMOVE_PATTERNS[11]
            return CleanCandidate(
                relative_path=relative_path,
                rule=rule,
                is_dir=False,
                age_days=age_days,
            )

        if entry_name.endswith(".safetensors.tmp"):
            age_days = self._get_age_days(entry, result)
            if age_days is None or age_days < self.TEMP_RETENTION_DAYS:
                return None
            return CleanCandidate(
                relative_path=relative_path,
                rule=self.REMOVE_PATTERNS[12],
                is_dir=False,
                age_days=age_days,
            )

        if entry_name.endswith(".descriptions.jsonl.tmp"):
            age_days = self._get_age_days(entry, result)
            if age_days is None or age_days < self.TEMP_RETENTION_DAYS:
                return None
            return CleanCandidate(
                relative_path=relative_path,
                rule=self.REMOVE_PATTERNS[13],
                is_dir=False,
                age_days=age_days,
            )

        return None

    def _get_age_days(self, entry: Path, result: CleanResult) -> float | None:
        try:
            modified_at = datetime.fromtimestamp(entry.lstat().st_mtime, tz=timezone.utc)
        except OSError as exc:
            relative_path = entry.relative_to(self.repo_root).as_posix()
            result.errors.append(f"Failed to stat {relative_path}: {exc}")
            return None

        age = datetime.now(timezone.utc) - modified_at
        return age.total_seconds() / 86400

    def _execute_candidates(self, result: CleanResult) -> None:
        self.clean_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.clean_log_path.touch(exist_ok=True)

        for candidate in result.candidates:
            target = self.repo_root / candidate.relative_path

            if not target.exists() and not target.is_symlink():
                result.errors.append(f"Missing cleanup target: {candidate.relative_path}")
                continue

            try:
                if candidate.is_dir:
                    shutil.rmtree(target)
                else:
                    target.unlink()
                result.deleted_paths.append(candidate.relative_path)
            except OSError as exc:
                result.errors.append(f"Failed to delete {candidate.relative_path}: {exc}")
                continue

            try:
                self._append_clean_log(candidate)
            except OSError as exc:
                result.errors.append(f"Deleted {candidate.relative_path} but failed to write clean log: {exc}")

    def _append_clean_log(self, candidate: CleanCandidate) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.clean_log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{timestamp}\tDELETE\t{candidate.rule}\t{candidate.relative_path}\n"
            )

    def _is_protected(self, relative_path: str) -> bool:
        for keep_entry in self.KEEP_ALWAYS:
            if relative_path == keep_entry or relative_path.startswith(f"{keep_entry}/"):
                return True
        return False

    def _is_internal_skip(self, relative_path: str) -> bool:
        return any(
            relative_path == skip_entry or relative_path.startswith(f"{skip_entry}/")
            for skip_entry in self.INTERNAL_SKIP | self.OUT_OF_SCOPE_ROOTS
        )

    @staticmethod
    def _is_real_directory(entry: Path) -> bool:
        return entry.is_dir() and not entry.is_symlink()

    def _print_summary(
        self,
        heading: str,
        result: CleanResult,
        *,
        include_candidates: bool,
    ) -> None:
        print("=" * 72)
        print(heading)
        print("-" * 72)
        print(f"Mode: {'dry-run' if result.dry_run else 'execute'}")
        print(f"Repo root: {self.repo_root}")
        print(f"Scanned paths: {result.scanned_paths}")
        print(f"Protected paths skipped: {result.protected_paths}")
        print(f"Matched candidates: {result.matched_paths}")
        print(f"Candidate directories: {result.directory_candidates}")
        print(f"Candidate files: {result.file_candidates}")
        print(f"Eligible log files (>= {self.LOG_RETENTION_DAYS} days): {result.eligible_log_candidates}")
        print(f"Eligible temp sidecars (>= {self.TEMP_RETENTION_DAYS} day): {self._eligible_temp_candidates(result)}")

        if include_candidates and result.candidates:
            print("Candidates:")
            for candidate in result.candidates:
                print(f"  - {candidate.describe()}")

        if result.errors:
            print("Errors:")
            for error in result.errors:
                print(f"  - {error}")

    def _print_execution_result(self, result: CleanResult) -> None:
        print("=" * 72)
        print("Execution result")
        print("-" * 72)
        print(f"Deleted paths: {len(result.deleted_paths)}")
        print(f"Deletion log: {self.clean_log_path}")

        if result.deleted_paths:
            print("Deleted entries:")
            for relative_path in result.deleted_paths:
                print(f"  - {relative_path}")

        if result.errors:
            print("Execution errors:")
            for error in result.errors:
                print(f"  - {error}")

    def _eligible_temp_candidates(self, result: CleanResult) -> int:
        return sum(
            1
            for candidate in result.candidates
            if candidate.rule in {self.REMOVE_PATTERNS[12], self.REMOVE_PATTERNS[13]}
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely clean repo-generated artifacts.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup without deleting files or directories. This is the default mode.",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Delete matched files and directories.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    cleaner = RepoClean(repo_root=repo_root, dry_run=not args.execute)
    return cleaner.run()


if __name__ == "__main__":
    raise SystemExit(main())
