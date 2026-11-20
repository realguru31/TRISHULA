"""Single source of truth for the TRISHULA version (semantic versioning).

MAJOR.MINOR.PATCH — PATCH: fixes · MINOR: new features/tabs · MAJOR: breaking data or layout changes.
Bump here AND add a CHANGELOG.md entry with every change.
"""
VERSION = "0.41.0"
BUILD_DATE = "2026-11-20"
LABEL = f"TRISHULA v{VERSION} ({BUILD_DATE})"
# v0.37.0: the standalone SPX BB app has its own number, so an SPX BB-only change never restarts TRISHULA's recorder
BB_VERSION = "0.47.2"
