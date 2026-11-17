"""CLAUDE.md, "Who does what": Claude never pushes to `main`, never pushes with force, never deletes a branch and never
merges, and the deny rules in `.claude/settings.json` block these from Bash and PowerShell. Spec 004, J14, names the
deny rule on merging. So the deny list holds a fixed set of patterns, each for both shells, and every Bash rule for git
or gh has a PowerShell twin. The rules match command text only, so they are best effort (CLAUDE.md)."""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED = [
    # Force pushes, also by a "+" refspec.
    "git push --force*", "git push -f*", "git push * --force*", "git push * -f*", "git push * +*",
    # Deleting a remote branch, also by an empty source refspec such as "origin :name".
    "git push --delete*", "git push * --delete*", "git push -d*", "git push * -d *", "git push * :*",
    # Pushes to main.
    "git push * main", "git push * main *", "git push * HEAD:main*",
    # Deleting a local branch, in any form.
    "git branch -D*", "git branch -d*", "git branch --delete*",
    # Merging a pull request.
    "gh pr merge*",
]


def _deny():
    return json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]


def test_J14_the_deny_list_holds_every_required_pattern_for_both_shells():
    deny = _deny()
    missing = [f"{shell}({p})" for p in REQUIRED for shell in ("Bash", "PowerShell") if f"{shell}({p})" not in deny]
    assert not missing, missing


def test_J14_every_bash_deny_rule_for_git_and_merging_has_a_powershell_twin():
    deny = _deny()
    bash = [m.group(1) for rule in deny if (m := re.fullmatch(r"Bash\(((?:git|gh) .+)\)", rule))]
    assert bash
    missing = [pattern for pattern in bash if f"PowerShell({pattern})" not in deny]
    assert not missing, missing
