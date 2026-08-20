# Release Checklist

Voice Buddy ships as a Claude Code plugin. A marketplace install copies the
repository onto the user's disk, so "release" means the repository itself is
correct — there is no separate build to gate.

Run this before tagging. Everything here is either enforced by CI or verified
by hand once per release; the split is marked on each item.

---

## 1. Version bump

The version appears in three files and **all three must agree** — the listener
writes `__version__` into `listener.version` and compares it on every
SessionStart, so a drift makes the supervisor retire and respawn the listener
every session.

- [ ] `.claude-plugin/plugin.json` → `"version"`
- [ ] `pyproject.toml` → `version`
- [ ] `voice_buddy/__init__.py` → `__version__`

*Enforced by CI:* `tests/test_release_gate.py::test_version_is_identical_in_every_source`

```bash
python3 -m pytest tests/test_release_gate.py -v
```

## 2. Dependencies

- [ ] If any range in `pyproject.toml` changed, regenerate the lock **on the
      floor interpreter**:

      PYTHON=python3.10 bash scripts/regen-constraints.sh

      Resolving on a newer version silently drops `python_version < "3.11"`
      transitives, producing pins that fail on 3.10 — the one version they
      exist to certify.

- [ ] `requirements.txt` / `requirements-dev.txt` still mirror `pyproject.toml`.
- [ ] `python3 -m pip_audit` reports no known vulnerabilities.

*Enforced by CI:* `tests/test_packaging.py` (parity, closure, pin exactness)

## 3. Tests and validation

- [ ] Full suite green on the supported matrix (3.10 – 3.14).
- [ ] Both plugin manifests validate **individually**:

      claude plugin validate .claude-plugin/plugin.json --strict
      claude plugin validate .claude-plugin/marketplace.json --strict

      `claude plugin validate .` only checks `marketplace.json` when both files
      exist — it silently skips `plugin.json`.

*Enforced by CI:* the `test` and `plugin-validation` jobs.

## 4. Artifact hygiene

- [ ] No developer-local paths, caches, credentials, or project-local
      `.claude/` configuration in tracked files.

*Enforced by CI:* the hygiene tests in `tests/test_release_gate.py`, plus the
`packaging` job's inspection of the built wheel and sdist.

## 5. Documentation

- [ ] English and Chinese sections both updated — prerequisites, install,
      upgrade, uninstall, dependencies, permissions, troubleshooting.
- [ ] No hardcoded test counts or version numbers in prose (they go stale; CI
      prints the real ones).
- [ ] `docs/manual-tests.md` covers any changed hotkey or lifecycle behavior.

*Partly enforced by CI:* README claims about the Python range, hook events,
CLI commands and the pyobjc install command are checked against the repository.

## 6. Manual smoke test (macOS)

CI cannot grant Accessibility or press a key, so this is done by hand on the
supported Claude Code baseline. Full steps: `docs/manual-tests.md`.

- [ ] **Clean install** — `/plugin marketplace add luyao618/voice-buddy` then
      `/plugin install voice-buddy`; confirm 1 skill, 7 agents, 4 hooks.
- [ ] **Upgrade** — from the previous version; `version handshake` shows the
      new version and exactly one listener is running (AC15).
- [ ] **Uninstall** — plugin is removed; the user's `config.json` under
      `~/Library/Application Support/voice-buddy/` is intentionally kept.
- [ ] **Hotkey** — F2 stops playback (AC1–AC12 in `docs/manual-tests.md`).

> **Upgrade gotcha.** `claude plugin update voice-buddy` fails with
> `Plugin "voice-buddy" not found`; the fully-qualified form works:
>
>     claude plugin update voice-buddy@voice-buddy-marketplace
>
> Also note the installed version is resolved from the marketplace entry's
> source. For the published `github` source, an update only appears after the
> bump is **pushed** — editing a local clone changes nothing.

## 7. Tag and publish

- [ ] Commit the version bump and any regenerated `constraints.txt`.
- [ ] Tag: `claude plugin tag .` validates that `plugin.json` and the
      marketplace entry agree, then creates `voice-buddy--v<version>`.
- [ ] Push the tag. Users on the `github` source receive the update once the
      bumped `plugin.json` is on the default branch.

---

## What CI covers

| Job | Checks |
|-----|--------|
| `test` | Full suite on 3.10–3.14 (macOS) plus 3.10 and 3.14 on Linux, installed against `constraints.txt`; blocking `pip-audit` advisory scan |
| `plugin-validation` | Both manifests with `--strict`, individually; component inventory and hook-timeout units |
| `packaging` | Wheel and sdist build; **artifact contents** unpacked and scanned for credentials and developer paths; clean-env install; hooks exit 0 with pyobjc absent |
| `install-from-source` | Constrained install on the 3.10 floor; `constraints.txt` closure |

**Platform coverage, precisely.** macOS runs the full Python range; Linux runs
the endpoints. **There is no Windows runner.** `win32` appears only as a
*simulated* platform inside
`test_supervisor_is_a_no_op_off_darwin`, which asserts the supervisor is a
clean no-op — that is a contract test, not install or runtime coverage. 32 of
the existing tests assume POSIX primitives (`ps`, `flock`, `/`-separated
paths), so a Windows runner reports failures without finding real defects.
Windows is documented as best-effort in the README and must not be described
as verified.

What CI cannot cover, and why: macOS Accessibility permission, a real F2
keypress, and audible playback. Those stay in `docs/manual-tests.md`.

## Dependency advisory exceptions

`pip-audit` is **blocking**. If a known vulnerability appears:

1. Preferred — bump the dependency and regenerate `constraints.txt` on the
   floor interpreter.
2. If the fix cannot be taken yet, add the advisory id to `.pip-audit-ignore`
   with the rationale, the reviewer, and the condition for removing it. The
   file's header states the required format; entries without a justification
   should not pass review.

Nothing is waived silently — an empty `.pip-audit-ignore` means the gate is
running at full strength.
