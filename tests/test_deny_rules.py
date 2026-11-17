"""CLAUDE.md, "Who does what": Claude never pushes to `main`, never pushes with force, never deletes a branch and never
merges, and the deny rules in `.claude/settings.json` block these from Bash and PowerShell. So the deny list holds a
fixed set of patterns for git and gh, each for both shells, no rule blocks a command Claude may run, and every rule for
git or gh has a twin in the other shell. The rules match command text only, so they are best effort (CLAUDE.md, and
Claude Code's permissions page: deny rules cover "the invocation Claude usually produces and isn't a security
boundary")."""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _deny():
    return json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]


# CLAUDE.md, "Who does what": the required deny patterns for git and gh, each for both shells. Forms left uncovered,
# as best effort: colon refspecs such as `origin :x` and `feat:main`, combined flags such as `-uf`, and `git -C . push`.
REQUIRED_FOR_GIT_AND_GH = [
    # Force pushes, also by a "+" refspec.
    "git push --force*", "git push -f*", "git push * --force*", "git push * -f*", "git push * +*",
    # Deleting a remote branch.
    "git push --delete*", "git push * --delete*", "git push --delete *", "git push -d*", "git push -d *",
    "git push * -d *",
    # Pruning or mirroring, which can delete remote branches.
    "git push --prune*", "git push * --prune*", "git push --mirror*", "git push * --mirror*",
    # Pushes to main.
    "git push * main", "git push * main *", "git push * HEAD:main*",
    # Deleting a local branch, with the flag first or later.
    "git branch -D*", "git branch -d*", "git branch --delete*", "git branch * -D*", "git branch * -d*",
    "git branch * --delete*",
    # Merging a pull request.
    "gh pr merge*",
]

# Commands CLAUDE.md lets Claude run, which no deny rule may block.
ALLOWED = [
    "git push -u origin docs/x", "git push -q -u origin docs/x", "git push origin docs/x", "git push",
    "git branch", "git branch -a", "gh pr create --draft", "gh pr comment 1", "gh pr ready 1",
]


def _matches(rule, command):
    """Claude Code's matching, from its permissions page (code.claude.com/docs/en/permissions.md): a `*` matches any
    text, spaces included, a trailing `:*` is the same as ` *`, every other character is literal, and PowerShell rules
    match without regard to case."""
    shell, pattern = re.fullmatch(r"(Bash|PowerShell)\((.*)\)", rule).groups()
    if pattern.endswith(":*"):
        pattern = pattern[:-2] + " *"
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.fullmatch(regex, command, flags=re.I if shell == "PowerShell" else 0) is not None


def _git_and_gh(deny, shell):
    return {m.group(1) for rule in deny if (m := re.fullmatch(rf"{shell}\(((?:git|gh) .+)\)", rule))}


def test_who_does_what_the_deny_list_holds_every_required_pattern_for_git_and_gh_in_both_shells():
    deny = _deny()
    missing = [f"{shell}({p})" for p in REQUIRED_FOR_GIT_AND_GH for shell in ("Bash", "PowerShell")
               if f"{shell}({p})" not in deny]
    assert not missing, missing


def test_who_does_what_no_deny_rule_blocks_a_command_claude_may_run():
    rules = [rule for rule in _deny() if re.fullmatch(r"(Bash|PowerShell)\(.*\)", rule)]
    blocked = [(rule, command) for rule in rules for command in ALLOWED if _matches(rule, command)]
    assert not blocked, blocked


def test_who_does_what_the_matcher_follows_the_permissions_page():
    assert _matches("Bash(git push * -d *)", "git push origin -d x")
    assert not _matches("Bash(git push * -d *)", "git push -d origin x")
    assert _matches("Bash(ls:*)", "ls -la") and _matches("Bash(ls *)", "ls -la")
    assert _matches("PowerShell(git branch -D*)", "git branch -d x")
    assert not _matches("Bash(git branch -D*)", "git branch -d x")


def test_who_does_what_every_deny_rule_for_git_and_gh_has_a_twin_in_the_other_shell():
    deny = _deny()
    bash, powershell = _git_and_gh(deny, "Bash"), _git_and_gh(deny, "PowerShell")
    assert bash and powershell
    assert bash == powershell, (sorted(bash - powershell), sorted(powershell - bash))
