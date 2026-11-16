"""CLAUDE.md, "Who does what", and spec 004, J14: the deny rules in `.claude/settings.json` block force pushes,
pushes to `main`, branch deletion and merging from both Bash and PowerShell. So every Bash rule of that kind has a
PowerShell twin with the same pattern."""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_J14_every_bash_deny_rule_for_git_and_merging_has_a_powershell_twin():
    deny = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
    bash = [m.group(1) for rule in deny if (m := re.fullmatch(r"Bash\(((?:git|gh) .+)\)", rule))]
    assert bash
    missing = [pattern for pattern in bash if f"PowerShell({pattern})" not in deny]
    assert not missing, missing
