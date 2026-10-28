"""Hooks: test gate, data guard, read guard and final guard.

The hook scripts live in `.claude/hooks/` and are loaded here by path.
Each guard has a pure `decide()` function that returns None to allow, or a
(decision, reason) pair where decision is "deny" or "ask".

The test gate itself runs as a git pre-commit hook, because git knows which
files will really be committed in every commit form. The Claude hook only
blocks ways around it (`--no-verify`, changing `core.hooksPath`) and refuses
a commit while the git hook is not installed.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from voc.repo_checks import CFPB_HEADER

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate():
    return _load("test_gate")


@pytest.fixture
def data_guard():
    return _load("data_guard")


@pytest.fixture
def read_guard():
    return _load("read_guard")


def _fake_key():
    return "sk-" + "ant-" + "api03-" + "Q" * 40  # built at run time, never one string


def _row(complaint_id):
    return ",".join(["2026-07-01", "Credit card"] + [""] * 13 + [complaint_id])


# Test gate, Claude side: block ways around the git hook


@pytest.mark.parametrize("tool, command", [
    ("Bash", "git commit --no-verify -m x"),
    ("Bash", "git commit -nm x"),
    ("Bash", "git commit -a -n -m x"),
    ("PowerShell", "git commit --no-verify -m x; if ($?) { git push }"),
    ("Bash", "git -c core.hooksPath=/dev/null commit -m x"),
    ("Bash", "git config core.hooksPath other"),
    ("PowerShell", "git config --unset core.hooksPath"),
])
def test_ways_around_the_git_hook_are_blocked(gate, tool, command):
    decision = gate.decide(tool, {"command": command}, hooks_path=".githooks")
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("tool, command", [
    ("Bash", "git commit -m x"),
    ("Bash", "git -C . commit -m x"),
    ("Bash", "git commit -a -m x"),
    ("Bash", "git commit src/a.py -m x"),
    ("Bash", "cd sub && git add -A && git commit -q -m x"),
    ("PowerShell", "git commit -m x; if ($?) { git log -1 }"),
])
def test_a_commit_in_any_form_is_refused_while_the_git_hook_is_not_installed(gate, tool, command):
    decision = gate.decide(tool, {"command": command}, hooks_path=None)
    assert decision and decision[0] == "deny"
    assert "core.hooksPath" in decision[1]
    assert gate.decide(tool, {"command": command}, hooks_path=".githooks") is None


def test_a_command_that_is_not_a_commit_is_allowed_without_the_hook(gate):
    assert gate.decide("Bash", {"command": "git status"}, hooks_path=None) is None
    assert gate.decide("Bash", {"command": "git log -m"}, hooks_path=None) is None


@pytest.mark.parametrize("command", [
    'git -C "my dir" commit -n -m x',
    "git commit --no-veri -m x",
])
def test_rare_forms_that_skip_the_git_hook_are_blocked(gate, command):
    decision = gate.decide("Bash", {"command": command}, hooks_path=".githooks")
    assert decision and decision[0] == "deny"


def test_a_commit_message_that_mentions_n_is_allowed(gate):
    command = 'git commit -m "add -n flag docs"'
    assert gate.decide("Bash", {"command": command}, hooks_path=".githooks") is None


# Test gate, git side: the tests run on the files that will really be committed


def _git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo, check=True, capture_output=True, text=True, env=env)


def _write(repo, path, text):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


PROJECT = {
    "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n',
    "src/mod.py": "def f():\n    return 1\n",
    "tests/test_mod.py": "from mod import f\n\n\ndef test_f():\n    assert f() == 1\n",
    "tests/test_env.py": (
        "import os\n\n\ndef test_no_git_variables_leak_into_the_tests():\n"
        "    assert [k for k in os.environ if k.startswith('GIT_')] == []\n"),
}


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for path, text in PROJECT.items():
        _write(repo, path, text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    return repo


def _stage(repo, path, text):
    _write(repo, path, text)
    _git(repo, "add", "-A")


def test_a_commit_is_blocked_when_tests_fail(gate, project):
    _stage(project, "src/mod.py", "def f():\n    return 2\n")
    assert gate.check_staged(project)


def test_a_commit_is_allowed_when_tests_pass(gate, project):
    _stage(project, "src/mod.py", "def f():\n    return 1  # same\n")
    assert gate.check_staged(project) == []


def test_only_the_staged_files_are_tested_not_the_working_tree(gate, project):
    _stage(project, "src/mod.py", "def f():\n    return 1  # staged\n")
    _write(project, "src/mod.py", "def f():\n    return 99\n")  # not staged
    assert gate.check_staged(project) == []
    _write(project, "src/mod.py", "def f():\n    return 1\n")
    _stage(project, "src/mod.py", "def f():\n    return 99\n")
    _write(project, "src/mod.py", "def f():\n    return 1\n")  # fixed only in the working tree
    assert gate.check_staged(project)


def test_a_tests_only_commit_with_only_new_failing_tests_is_allowed(gate, project):
    _stage(project, "tests/test_mod.py", PROJECT["tests/test_mod.py"]
           + "\n\ndef test_g():\n    from mod import g\n    assert g() == 2\n")
    assert gate.check_staged(project) == []


def test_a_new_test_file_that_cannot_import_yet_is_allowed(gate, project):
    _stage(project, "tests/test_new.py", "from mod import g\n\n\ndef test_g():\n    assert g() == 2\n")
    assert gate.check_staged(project) == []


def _red_commit(repo):
    """Commit a failing new test without the gate, as an earlier red test commit."""
    _stage(repo, "tests/test_mod.py", PROJECT["tests/test_mod.py"]
           + "\n\ndef test_g():\n    from mod import g\n    assert g() == 2\n")
    _git(repo, "commit", "-q", "-m", "red")


def test_a_second_red_commit_may_keep_tests_that_were_already_failing(gate, project, capsys):
    _red_commit(project)
    _stage(project, "tests/test_more.py", "def test_h():\n    from mod import h\n    assert h() == 3\n")
    assert gate.check_staged(project) == []
    out = capsys.readouterr().out
    assert "carried-over failing test" in out and "test_g" in out


def test_a_red_commit_may_still_not_delete_a_test_that_was_already_failing(gate, project):
    _red_commit(project)
    _stage(project, "tests/test_mod.py", PROJECT["tests/test_mod.py"])
    assert gate.check_staged(project)


@pytest.mark.parametrize("marker", ["skip", "xfail"])
def test_a_red_commit_may_not_turn_an_already_failing_test_into_a_skip(gate, project, marker):
    _red_commit(project)
    _stage(project, "tests/test_mod.py", "import pytest\n" + PROJECT["tests/test_mod.py"]
           + f"\n\n@pytest.mark.{marker}\ndef test_g():\n    from mod import g\n    assert g() == 2\n")
    assert gate.check_staged(project)


def test_test_files_hidden_by_export_ignore_are_still_run(gate, project):
    _stage(project, ".gitattributes", "tests/test_mod.py export-ignore\n")
    _stage(project, "src/mod.py", "def f():\n    return 2\n")
    assert gate.check_staged(project)


def test_a_tests_only_commit_that_breaks_an_existing_test_is_blocked(gate, project):
    _stage(project, "tests/test_mod.py", "from mod import f\n\n\ndef test_f():\n    assert f() == 3\n")
    assert gate.check_staged(project)


def test_a_tests_only_commit_that_deletes_a_test_is_blocked(gate, project):
    _stage(project, "tests/test_mod.py", "def test_other():\n    assert True\n")
    assert gate.check_staged(project)
    _git(project, "reset", "-q", "--hard")
    _git(project, "rm", "-q", "tests/test_mod.py")
    assert gate.check_staged(project)


def test_a_tests_only_commit_that_makes_an_existing_test_skip_is_blocked(gate, project):
    _stage(project, "tests/test_mod.py",
           "import pytest\nfrom mod import f\n\n\n@pytest.mark.skip\ndef test_f():\n    assert f() == 1\n")
    assert gate.check_staged(project)


def test_a_conftest_or_fixture_change_is_gated_like_code(gate, project):
    _stage(project, "tests/conftest.py", "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef boom():\n    raise RuntimeError\n")
    assert gate.check_staged(project)
    _git(project, "reset", "-q", "--hard")
    _stage(project, "tests/fixtures/a.txt", "x\n")
    _stage(project, "tests/test_new.py", "def test_new():\n    assert False\n")
    assert gate.check_staged(project), "a new failing test is not allowed next to a non-test change"


def test_a_staged_name_from_the_deny_list_is_blocked_and_not_printed(gate, project, capsys):
    _stage(project, "notes.md", "written by Qwertyname\n")
    problems = gate.check_staged(project, names=["Qwertyname"])
    assert problems
    assert all("qwertyname" not in p.lower() for p in problems)


def test_the_git_hook_fails_if_gitleaks_is_not_installed(gate, project, tmp_path):
    env = dict(os.environ, PATH=str(tmp_path / "empty"), NAMES_DENYLIST="Qwertyname")
    assert gate.git_pre_commit(project, env) != 0


# The git hook through a real `git commit`, so `-a` and `git commit <path>` are covered


@pytest.fixture
def hooked(project, tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    python = Path(sys.executable).as_posix()
    script = (HOOKS / "test_gate.py").as_posix()
    for name in ("pre-commit", "pre-merge-commit"):
        hook = hooks / name
        hook.write_text(f'#!/bin/sh\nexec "{python}" "{script}" --git-pre-commit\n', encoding="utf-8")
        hook.chmod(0o755)
    fake = tmp_path / "fakebin"
    fake.mkdir()
    if sys.platform == "win32":
        (fake / "gitleaks.bat").write_text("@exit /b 0\r\n", encoding="utf-8")
    else:
        (fake / "gitleaks").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (fake / "gitleaks").chmod(0o755)
    _git(project, "config", "core.hooksPath", hooks.as_posix())
    env = dict(os.environ, NAMES_DENYLIST="Qwertyname")
    env["PATH"] = str(fake) + os.pathsep + env["PATH"]
    return project, env


def _commit(repo, env, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", *args],
        cwd=repo, capture_output=True, text=True, env=env)


def test_the_git_hook_blocks_a_failing_commit_and_allows_a_passing_one(hooked):
    repo, env = hooked
    _stage(repo, "src/mod.py", "def f():\n    return 2\n")
    assert _commit(repo, env, "-m", "break").returncode != 0
    _stage(repo, "src/mod.py", "def f():\n    return 1  # ok\n")
    assert _commit(repo, env, "-m", "fine").returncode == 0


def test_a_merge_commit_runs_the_same_gate(hooked):
    repo, env = hooked
    _git(repo, "checkout", "-q", "-b", "side")
    _write(repo, "src/mod.py", "def f():\n    return 2\n")
    _git(repo, "commit", "-q", "-a", "-m", "break on a side branch", "--no-verify", env=env)
    _git(repo, "checkout", "-q", "main")
    _write(repo, "notes.md", "x\n")
    _git(repo, "add", "notes.md")
    assert _commit(repo, env, "-m", "main moves on").returncode == 0
    merge = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                            "merge", "--no-ff", "-q", "-m", "merge", "side"],
                           cwd=repo, capture_output=True, text=True, env=env)
    assert merge.returncode != 0


def test_the_real_merge_hook_runs_the_same_gate_as_the_commit_hook():
    githooks = HOOKS.parent.parent / ".githooks"
    commit_hook = (githooks / "pre-commit").read_text(encoding="utf-8")
    merge_hook = (githooks / "pre-merge-commit").read_text(encoding="utf-8")
    run_line = [line for line in commit_hook.splitlines() if "test_gate.py" in line]
    assert run_line and all(line in merge_hook for line in run_line)


def test_the_git_hook_checks_commit_a_and_commit_with_a_path(hooked):
    repo, env = hooked
    # First prove the hook runs and passes good work, so a failure below means a block.
    _write(repo, "src/mod.py", "def f():\n    return 1  # ok\n")
    assert _commit(repo, env, "-a", "-m", "fine").returncode == 0
    _write(repo, "src/mod.py", "def f():\n    return 2\n")  # changed, not staged
    assert _commit(repo, env, "-a", "-m", "break").returncode != 0
    assert _commit(repo, env, "-m", "break", "--", "src/mod.py").returncode != 0


# Data guard


@pytest.mark.parametrize("path", [".env", "config/.env", ".env.local"])
def test_writing_an_env_file_is_blocked(data_guard, tmp_path, path):
    decision = data_guard.decide("Write", {"file_path": str(tmp_path / path), "content": "X=1\n"}, root=tmp_path)
    assert decision and decision[0] == "deny"


def test_env_example_is_allowed_only_without_a_key_like_value(data_guard, tmp_path):
    path = str(tmp_path / ".env.example")
    assert data_guard.decide("Write", {"file_path": path, "content": "ANTHROPIC_API_KEY=\n"}, root=tmp_path) is None
    decision = data_guard.decide("Write", {"file_path": path, "content": f"ANTHROPIC_API_KEY={_fake_key()}\n"},
                                 root=tmp_path)
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("tool, field", [("Write", "content"), ("Edit", "new_string"), ("NotebookEdit", "new_source")])
def test_content_that_looks_like_an_anthropic_key_is_blocked(data_guard, tmp_path, tool, field):
    tool_input = {"file_path": str(tmp_path / "a.py"), "notebook_path": str(tmp_path / "a.ipynb"),
                  "old_string": "", field: f"key = '{_fake_key()}'\n"}
    decision = data_guard.decide(tool, tool_input, root=tmp_path)
    assert decision and decision[0] == "deny"
    assert _fake_key() not in decision[1]


def test_writing_a_file_with_the_cfpb_header_and_a_real_id_is_blocked(data_guard, tmp_path):
    content = CFPB_HEADER + "\n" + _row("12345678") + "\n"
    decision = data_guard.decide("Write", {"file_path": str(tmp_path / "notes/slice.csv"), "content": content},
                                 root=tmp_path)
    assert decision and decision[0] == "deny"


def test_an_edit_that_adds_a_real_row_to_a_fixture_is_blocked(data_guard, tmp_path):
    fixture = tmp_path / "tests/fixtures/f.csv"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(CFPB_HEADER + "\n" + _row("SYN-1") + "\n", encoding="utf-8")
    tool_input = {"file_path": str(fixture), "old_string": _row("SYN-1"),
                  "new_string": _row("SYN-1") + "\n" + _row("12345678")}
    decision = data_guard.decide("Edit", tool_input, root=tmp_path)
    assert decision and decision[0] == "deny"


def test_a_synthetic_fixture_is_allowed(data_guard, tmp_path):
    content = CFPB_HEADER + "\n" + _row("SYN-1") + "\n" + _row("SYN-2") + "\n"
    tool_input = {"file_path": str(tmp_path / "tests/fixtures/f.csv"), "content": content}
    assert data_guard.decide("Write", tool_input, root=tmp_path) is None


def test_a_normal_source_file_is_allowed(data_guard, tmp_path):
    tool_input = {"file_path": str(tmp_path / "src/voc/x.py"), "content": "def f():\n    return 1\n"}
    assert data_guard.decide("Write", tool_input, root=tmp_path) is None


@pytest.mark.parametrize("path", [
    ".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/read_guard.py", ".githooks/pre-commit",
])
def test_an_edit_to_settings_or_a_hook_script_asks_the_owner(data_guard, tmp_path, path):
    decision = data_guard.decide("Edit", {"file_path": str(tmp_path / path), "old_string": "a", "new_string": "b"},
                                 root=tmp_path)
    assert decision and decision[0] == "ask"


def test_an_edit_to_the_checks_the_guards_import_asks_the_owner(data_guard, tmp_path):
    tool_input = {"file_path": str(tmp_path / "src/voc/repo_checks.py"), "old_string": "a", "new_string": "b"}
    decision = data_guard.decide("Edit", tool_input, root=tmp_path, home=tmp_path / "home")
    assert decision and decision[0] == "ask"


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_an_edit_to_the_user_level_claude_settings_asks_the_owner(data_guard, tmp_path, name):
    home = tmp_path / "home"
    tool_input = {"file_path": str(home / ".claude" / name), "content": "{}\n"}
    decision = data_guard.decide("Write", tool_input, root=tmp_path / "repo", home=home)
    assert decision and decision[0] == "ask"


# Read guard (B21) and final guard (B17)


@pytest.fixture
def places(tmp_path):
    home = tmp_path / "home"
    data = tmp_path / "rawdata"
    (home / ".voc").mkdir(parents=True)
    data.mkdir()
    return {"home": home, "data": data, "root": tmp_path / "repo", "env": {"VOC_DATA_DIR": str(data)}}


def _read_decision(read_guard, places, tool, tool_input, env=None):
    return read_guard.decide(tool, tool_input, env=places["env"] if env is None else env,
                             home=places["home"], root=places["root"])


@pytest.mark.parametrize("tool, field", [("Read", "file_path"), ("Grep", "path"), ("Glob", "path")])
def test_B21_reading_the_raw_data_folder_is_blocked(read_guard, places, tool, field):
    decision = _read_decision(read_guard, places, tool, {field: str(places["data"] / "x.csv")})
    assert decision and decision[0] == "deny"


def test_B21_the_raw_data_folder_is_also_found_in_a_local_env_file(read_guard, places):
    places["root"].mkdir()
    (places["root"] / ".env").write_text(f"VOC_DATA_DIR={places['data']}\n", encoding="utf-8")
    decision = _read_decision(read_guard, places, "Read", {"file_path": str(places["data"] / "x.csv")}, env={})
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("path", ["work/voc.duckdb", "recordings/abc.json", "CCDB_Export_20_July_2026.csv"])
def test_B21_reading_the_duckdb_file_recordings_or_an_export_is_blocked(read_guard, places, path):
    decision = _read_decision(read_guard, places, "Read", {"file_path": str(places["root"] / path)})
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("tool, command", [
    ("Bash", "cat ~/.voc/ledger.json"),
    ("Bash", "head -c 100 $HOME/.voc/recordings/a.json"),
    ("Bash", 'ls "$VOC_DATA_DIR"'),
    ("Bash", "python -c \"import duckdb; duckdb.connect('work/voc.duckdb')\""),
    ("PowerShell", r"Get-Content $env:USERPROFILE\.voc\ledger.json"),
    ("PowerShell", r"type %USERPROFILE%\.voc\recordings\a.json"),
])
def test_B21_a_shell_command_naming_a_protected_path_is_blocked(read_guard, places, tool, command):
    decision = _read_decision(read_guard, places, tool, {"command": command})
    assert decision and decision[0] == "deny"


def test_B21_a_shell_command_with_the_full_data_folder_path_is_blocked(read_guard, places):
    command = "type " + str(places["data"]).replace("/", "\\") + "\\x.csv"
    decision = _read_decision(read_guard, places, "PowerShell", {"command": command})
    assert decision and decision[0] == "deny"


def test_B21_a_path_with_dot_dot_is_resolved_before_it_is_checked(read_guard, places):
    sneaky = str(places["root"] / ".." / "home" / "x" / ".." / ".voc" / "ledger.json")
    assert _read_decision(read_guard, places, "Read", {"file_path": sneaky})[0] == "deny"
    sneaky_data = str(places["data"] / ".." / places["data"].name / "a.csv")
    assert _read_decision(read_guard, places, "Read", {"file_path": sneaky_data})[0] == "deny"


@pytest.mark.parametrize("field", ["home", "data_parent"])
def test_B21_searching_a_folder_that_holds_a_protected_place_is_blocked(read_guard, places, field):
    folder = places["home"] if field == "home" else places["data"].parent
    for tool in ("Grep", "Glob"):
        decision = _read_decision(read_guard, places, tool, {"pattern": "x", "path": str(folder)})
        assert decision and decision[0] == "deny"


def test_B21_searching_the_repo_is_still_allowed(read_guard, places):
    assert _read_decision(read_guard, places, "Grep", {"pattern": "x", "path": str(places["root"])}) is None


@pytest.mark.parametrize("tool_input, expected", [
    ({"command": "cat ~/.voc/ledger.json"}, "deny"),
    ({"command": "uv run voc show 1"}, "deny"),
    ({"command": "uv run voc evaluate --final"}, "ask"),
])
def test_B21_any_tool_with_a_command_is_checked_like_a_shell(read_guard, places, tool_input, expected):
    decision = _read_decision(read_guard, places, "Monitor", tool_input)
    assert decision and decision[0] == expected


@pytest.mark.parametrize("tool, tool_input", [
    ("Artifact", {"file_paths": ["{voc}/recordings/a.json"]}),
    ("mcp__browser__upload_file", {"filePath": "{voc}/ledger.json"}),
    ("SomeTool", {"files": {"page.html": {"from": "{voc}/ledger.json"}}}),
])
def test_B21_every_path_in_any_tool_input_is_checked(read_guard, places, tool, tool_input):
    voc = str(places["home"] / ".voc")
    filled = json.loads(json.dumps(tool_input).replace("{voc}", voc.replace("\\", "/")))
    decision = _read_decision(read_guard, places, tool, filled)
    assert decision and decision[0] == "deny"


def test_B21_text_written_into_a_file_is_not_treated_as_a_path(read_guard, places):
    tool_input = {"file_path": str(places["root"] / "notes.md"), "content": "the ledger lives in ~/.voc/"}
    assert _read_decision(read_guard, places, "Write", tool_input) is None


@pytest.mark.parametrize("command", [
    "cd ~ && cat .voc/ledger.json",
    "Get-Content (Join-Path $HOME '.voc' 'ledger.json')",
    "head -3 /c/data/cfpb_2026_07/a.csv",
    "cd /c/data && head -3 cfpb_2026_07/a.csv",
])
def test_B21_more_shell_forms_of_protected_paths_are_blocked(read_guard, places, command):
    env = {"VOC_DATA_DIR": "C:\\data\\cfpb_2026_07"}
    decision = _read_decision(read_guard, places, "Bash", {"command": command}, env=env)
    assert decision and decision[0] == "deny"


def test_B21_a_single_ampersand_separates_commands(read_guard, places):
    decision = _read_decision(read_guard, places, "Bash", {"command": "git status & uv run voc show 1"})
    assert decision and decision[0] == "deny"


def test_B21_reading_the_home_ledger_folder_by_full_path_is_blocked(read_guard, places):
    decision = _read_decision(read_guard, places, "Read", {"file_path": str(places["home"] / ".voc" / "ledger.json")})
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("tool, command", [
    ("Bash", "uv run voc show SYN-1"),
    ("Bash", "python -m voc show 123"),
    ("Bash", "dbt show --select curated"),
    ("PowerShell", "uv run --native-tls voc show 123"),
    ("Bash", "git status && uv run voc show 1"),
])
def test_B21_running_show_is_blocked_outright(read_guard, places, tool, command):
    decision = _read_decision(read_guard, places, tool, {"command": command})
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("tool, tool_input", [
    ("Read", {"file_path": ".env"}),
    ("Grep", {"pattern": "KEY", "path": "config/.env"}),
    ("Bash", {"command": "cat .env"}),
    ("PowerShell", {"command": r"Get-Content C:\work\repo\.env"}),
])
def test_reading_the_env_file_with_the_key_is_blocked(read_guard, places, tool, tool_input):
    decision = _read_decision(read_guard, places, tool, tool_input)
    assert decision and decision[0] == "deny"


def test_reading_env_example_is_allowed(read_guard, places):
    assert _read_decision(read_guard, places, "Read", {"file_path": ".env.example"}) is None
    assert _read_decision(read_guard, places, "Bash", {"command": "cat .env.example"}) is None


def test_B21_git_show_and_normal_reads_are_allowed(read_guard, places):
    assert _read_decision(read_guard, places, "Bash", {"command": "git show --stat HEAD"}) is None
    assert _read_decision(read_guard, places, "Read", {"file_path": str(places["root"] / "README.md")}) is None
    assert _read_decision(read_guard, places, "Bash", {"command": "uv run pytest"}) is None


@pytest.mark.parametrize("command", ["uv run voc evaluate --final", "uv run voc evaluate final", "FINAL=1 make score"])
def test_B17_a_command_containing_final_asks_the_owner(read_guard, places, command):
    decision = _read_decision(read_guard, places, "Bash", {"command": command})
    assert decision and decision[0] == "ask"


def test_B17_a_word_that_only_contains_final_is_not_asked(read_guard, places):
    assert _read_decision(read_guard, places, "Bash", {"command": "echo finally finalise"}) is None


# T010 add-on 1: the next month's data folder (`VOC_NEXT_DATA_DIR`) is protected like July's


@pytest.fixture
def next_places(places, tmp_path):
    following = tmp_path / "rawnext_2026_08"
    following.mkdir()
    env = {"VOC_DATA_DIR": str(places["data"]), "VOC_NEXT_DATA_DIR": str(following)}
    return {**places, "next": following, "env": env}


@pytest.mark.parametrize("tool, field", [("Read", "file_path"), ("Grep", "path"), ("Glob", "path")])
def test_B21_reading_the_next_month_data_folder_is_blocked(read_guard, next_places, tool, field):
    decision = _read_decision(read_guard, next_places, tool, {field: str(next_places["next"] / "x.csv")})
    assert decision and decision[0] == "deny"


def test_B21_the_next_month_folder_is_blocked_when_only_it_is_set(read_guard, next_places):
    env = {"VOC_NEXT_DATA_DIR": str(next_places["next"])}
    decision = _read_decision(read_guard, next_places, "Read", {"file_path": str(next_places["next"] / "x.csv")},
                              env=env)
    assert decision and decision[0] == "deny"


def test_B21_the_next_month_folder_is_also_found_in_a_local_env_file(read_guard, next_places):
    next_places["root"].mkdir()
    (next_places["root"] / ".env").write_text(
        f"VOC_DATA_DIR={next_places['data']}\nVOC_NEXT_DATA_DIR={next_places['next']}\n", encoding="utf-8")
    decision = _read_decision(read_guard, next_places, "Read", {"file_path": str(next_places["next"] / "x.csv")},
                              env={})
    assert decision and decision[0] == "deny"


@pytest.mark.parametrize("command", [
    'ls "$VOC_NEXT_DATA_DIR"',
    r"Get-ChildItem $env:VOC_NEXT_DATA_DIR",
    "cd /c && head -3 rawnext_2026_08/a.csv",
])
def test_B21_a_shell_command_naming_the_next_month_folder_is_blocked(read_guard, next_places, command):
    decision = _read_decision(read_guard, next_places, "Bash", {"command": command})
    assert decision and decision[0] == "deny"


def test_B21_a_shell_command_with_the_full_next_month_path_is_blocked(read_guard, next_places):
    command = "type " + str(next_places["next"]).replace("/", "\\") + "\\x.csv"
    decision = _read_decision(read_guard, next_places, "PowerShell", {"command": command})
    assert decision and decision[0] == "deny"


def test_B21_searching_a_folder_that_holds_the_next_month_folder_is_blocked(read_guard, next_places, tmp_path):
    following = tmp_path / "elsewhere" / "rawnext_2026_08"
    following.mkdir(parents=True)
    env = {"VOC_DATA_DIR": str(next_places["data"]), "VOC_NEXT_DATA_DIR": str(following)}
    for tool in ("Grep", "Glob"):
        decision = _read_decision(read_guard, next_places, tool, {"pattern": "x", "path": str(following.parent)},
                                  env=env)
        assert decision and decision[0] == "deny"


# Each hook script fails closed


@pytest.mark.parametrize("name", ["test_gate", "data_guard", "read_guard"])
def test_a_hook_given_bad_input_blocks_with_exit_code_2(name):
    result = subprocess.run([sys.executable, str(HOOKS / f"{name}.py")], input="not json",
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "hook failed" in result.stderr  # our own message, not Python failing to start


@pytest.mark.parametrize("name", ["test_gate", "data_guard", "read_guard"])
@pytest.mark.parametrize("text", [
    "He said " + chr(0x201C) + "fine" + chr(0x201D) + " and left",
    # Regression cases only: on the old code these two did not fail (the first is plain ASCII,
    # the second decodes in cp932 into other characters). The test below checks the exact text.
    'PLAIN = {"' + "\\" + 'u201c": 1}',
    "Japanese text " + chr(0x8868) + chr(0x793A),
])
def test_each_hook_reads_its_input_as_utf8_whatever_the_system_encoding(name, text, tmp_path):
    # Claude Code sends UTF-8. On a Japanese Windows system Python would read it as cp932.
    event = {"tool_name": "Edit", "cwd": str(tmp_path),
             "tool_input": {"file_path": str(tmp_path / "a.py"), "old_string": "a", "new_string": text}}
    env = dict(os.environ, PYTHONIOENCODING="cp932", PYTHONUTF8="0")
    result = subprocess.run([sys.executable, str(HOOKS / f"{name}.py")],
                            input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                            capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"hook failed" not in result.stderr


def test_the_read_guard_sees_a_non_ascii_path_exactly_as_sent(tmp_path):
    # The curly-quote case above shows the decode error. This shows the quieter failure:
    # read as cp932, a Japanese folder name turns into other characters and the guard misses it.
    data = tmp_path / (chr(0x30C7) + chr(0x30FC) + chr(0x30BF))
    data.mkdir()
    event = {"tool_name": "Read", "cwd": str(tmp_path), "tool_input": {"file_path": str(data / "a.csv")}}
    env = dict(os.environ, PYTHONIOENCODING="cp932", PYTHONUTF8="0", VOC_DATA_DIR=str(data))
    result = subprocess.run([sys.executable, str(HOOKS / "read_guard.py")],
                            input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                            capture_output=True, env=env)
    assert b'"permissionDecision": "deny"' in result.stdout


def _hooked_worktree(tmp_path):
    main_checkout = tmp_path / "main"
    main_checkout.mkdir()
    _git(main_checkout, "init", "-q", "-b", "main")
    _write(main_checkout, ".githooks/pre-commit", "#!/bin/sh\nexit 0\n")
    _git(main_checkout, "add", "-A")
    _git(main_checkout, "commit", "-q", "-m", "first")
    worktree = tmp_path / "wt"
    _git(main_checkout, "worktree", "add", "-q", str(worktree), "-b", "side")
    return main_checkout, worktree


def _gate_says(cwd, hooks_value):
    _git(cwd, "config", "core.hooksPath", hooks_value)
    event = {"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": "git commit -m x"}}
    result = subprocess.run([sys.executable, str(HOOKS / "test_gate.py")],
                            input=json.dumps(event).encode("utf-8"), capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.decode("utf-8")


def test_a_real_worktree_with_the_full_hook_path_may_commit(tmp_path):
    main_checkout, worktree = _hooked_worktree(tmp_path)
    assert _gate_says(worktree, str(main_checkout / ".githooks")) == ""
    assert "deny" in _gate_says(worktree, str(tmp_path / "elsewhere" / ".githooks"))


def test_a_full_hook_path_without_a_pre_commit_hook_is_not_installed(tmp_path):
    main_checkout, worktree = _hooked_worktree(tmp_path)
    (main_checkout / ".githooks" / "pre-commit").unlink()
    assert "deny" in _gate_says(worktree, str(main_checkout / ".githooks"))


def test_the_git_hook_may_be_set_by_its_full_path(gate, tmp_path):
    repo, main_checkout = tmp_path / "worktree", tmp_path / "main"
    command = {"command": "git commit -m x"}
    for hooks in (repo / ".githooks", main_checkout / ".githooks"):
        assert gate.decide("Bash", command, hooks_path=str(hooks), roots=(repo, main_checkout)) is None
    decision = gate.decide("Bash", command, hooks_path=str(tmp_path / "elsewhere" / ".githooks"),
                           roots=(repo, main_checkout))
    assert decision and decision[0] == "deny"


@pytest.mark.skipif(shutil.which("sh") is None, reason="no sh on this PATH (CI has one)")
def test_the_hook_runner_turns_any_failure_into_exit_code_2():
    result = subprocess.run(["sh", str(HOOKS / "run.sh"), "read_guard.py"], input="not json",
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "hook failed" in result.stderr
    missing = subprocess.run(["sh", str(HOOKS / "run.sh"), "no_such_hook.py"], input="{}",
                             capture_output=True, text=True)
    assert missing.returncode == 2


def test_every_hook_is_wired_to_fail_closed():
    settings = json.loads((HOOKS.parent / "settings.json").read_text(encoding="utf-8"))
    wired = {}
    for group in settings["hooks"]["PreToolUse"]:
        for hook in group["hooks"]:
            assert hook["onFailure"] == "block"
            assert hook["command"].endswith("|| exit 2")
            script = hook["command"].split("run.sh\" ")[1].split()[0]
            wired[script] = group["matcher"]
    assert wired == {"read_guard.py": "*", "test_gate.py": "Bash|PowerShell",
                     "data_guard.py": "Write|Edit|MultiEdit|NotebookEdit"}


def test_a_hook_prints_a_deny_decision_as_json(read_guard):
    result = subprocess.run([sys.executable, str(HOOKS / "read_guard.py")],
                            input='{"tool_name": "Bash", "tool_input": {"command": "dbt show"}, "cwd": "."}',
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '"permissionDecision": "deny"' in result.stdout
