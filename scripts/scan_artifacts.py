"""Scan built artifacts for secrets and developer-specific paths.

The packaging job previously inspected archive *member names* only, so a
credential embedded in a shipped source file passed the gate: an AWS key, a
GitHub token and a foreign developer's home path all reached the wheel while
the check reported "clean". This unpacks each archive and scans the text.

Used by both `tests/test_release_gate.py` and the CI packaging job, so the same
rules apply locally and on a runner.
"""
from __future__ import annotations

import re
import tarfile
import zipfile
from pathlib import Path

# Binary payloads have no text to scan and would produce noise.
SKIP_SUFFIXES = {".mp3", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip",
                 ".gz", ".so", ".dylib", ".pyc", ".woff", ".woff2", ".ico"}

# Each rule is (name, compiled pattern). Kept deliberately narrow: a rule that
# fires on ordinary prose gets muted, and a muted rule protects nothing.
SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
                       r"[A-Za-z0-9_-]{10,}\b")),
    # Assignment of a long opaque value to a secret-shaped name.
    ("assigned-secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
        r"client[_-]?secret|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+]{16,}['\"]")),
]

# Any user's home directory, not just the machine running the scan. A path
# baked in by one developer must fail on every other developer's checkout.
HOME_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9._-]+")

# Synthetic values that tests deliberately contain. These are the fixtures that
# *prove* real secrets are not leaked, so flagging them would force the checks
# to be deleted. Anything not on this list is treated as a real finding.
#
# Each entry is a literal, not a pattern: an entry broad enough to match a real
# secret would silently disarm the scanner.
ALLOWED_SYNTHETIC = {
    # Log-hygiene fixtures: hostile inputs asserted never to reach the log.
    "/Users/victim",
    # Documented payload examples transcribed from the Claude Code hook schema.
    "/Users/u",
    "/Users/...",
    # Windows config-path fixture in tests/test_config.py.
    r"C:\Users\test",
    r"C:\\Users\\test",
}

# AWS's own published example key, used in the adversarial log-hygiene test to
# prove a credential-shaped prompt never reaches the debug log. It is the
# canonical non-secret; matching it here would delete the test that protects
# real ones.
ALLOWED_SECRET_LITERALS = {"AKIAIOSFODNN7EXAMPLE"}


def _is_allowed(match: str) -> bool:
    return any(match.startswith(a) for a in ALLOWED_SYNTHETIC)


def scan_text(name: str, text: str) -> list[str]:
    """Return a list of findings for one file's contents."""
    findings = []
    for label, pattern in SECRET_PATTERNS:
        for hit in pattern.findall(text):
            excerpt = hit if isinstance(hit, str) else str(hit)
            if excerpt in ALLOWED_SECRET_LITERALS:
                continue
            if any(a in excerpt for a in ALLOWED_SECRET_LITERALS):
                continue
            findings.append(f"{name}: {label} -> {excerpt[:24]}…")
    for hit in HOME_PATH_PATTERN.findall(text):
        if not _is_allowed(hit):
            findings.append(f"{name}: developer-home-path -> {hit}")
    return findings


def iter_archive_text(archive: Path):
    """Yield `(member_name, text)` for every text member of a wheel or sdist."""
    if archive.suffix == ".whl" or archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir() or Path(info.filename).suffix in SKIP_SUFFIXES:
                    continue
                try:
                    yield info.filename, z.read(info).decode("utf-8")
                except (UnicodeDecodeError, KeyError):
                    continue
    else:
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                if not member.isfile() or Path(member.name).suffix in SKIP_SUFFIXES:
                    continue
                handle = t.extractfile(member)
                if handle is None:
                    continue
                try:
                    yield member.name, handle.read().decode("utf-8")
                except UnicodeDecodeError:
                    continue


def scan_archive(archive: Path) -> list[str]:
    """Return every finding inside one built artifact."""
    findings = []
    for name, text in iter_archive_text(archive):
        findings.extend(scan_text(f"{archive.name}:{name}", text))
    return findings


def scan_dist(dist_dir: Path) -> list[str]:
    findings = []
    for archive in sorted(dist_dir.iterdir()):
        if archive.suffix in {".whl", ".gz", ".zip"}:
            findings.extend(scan_archive(archive))
    return findings


def main() -> int:
    import sys

    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not dist.is_dir():
        print(f"error: {dist} is not a directory", file=sys.stderr)
        return 2

    archives = [p for p in dist.iterdir() if p.suffix in {".whl", ".gz", ".zip"}]
    if not archives:
        print(f"error: no artifacts found in {dist}", file=sys.stderr)
        return 2

    findings = scan_dist(dist)
    if findings:
        print("Artifact content scan FAILED:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1

    scanned = sum(1 for a in archives for _ in iter_archive_text(a))
    print(f"Artifact content scan clean "
          f"({len(archives)} archive(s), {scanned} text members)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
