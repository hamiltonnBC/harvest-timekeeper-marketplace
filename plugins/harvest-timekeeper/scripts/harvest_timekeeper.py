#!/usr/bin/env python3
"""Harvest time entry helper for Codex automations.

No third-party dependencies. Reads HARVEST_ACCESS_TOKEN from the environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = os.environ.get("HARVEST_API_BASE", "https://api.harvestapp.com/api/v2")
ID_BASE = "https://id.getharvest.com/api/v2"
DEFAULT_REPO = str(Path.cwd())
DEFAULT_USER_AGENT = "Codex Harvest Timekeeper"
DEFAULT_NOTE_PREFIX = ""
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "harvest-timekeeper" / "config.json"


class HarvestApiError(Exception):
    def __init__(self, method: str, url: str, code: int, detail: str):
        super().__init__(f"Harvest API {method} {url} failed with HTTP {code}: {detail}")
        self.method = method
        self.url = url
        self.code = code
        self.detail = detail


def config_path(value: str | None = None) -> Path:
    return Path(value or os.environ.get("HARVEST_TIMEKEEPER_CONFIG") or DEFAULT_CONFIG_PATH).expanduser()


def load_config(path_value: str | None = None) -> dict[str, Any]:
    path = config_path(path_value)
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def save_config(config: dict[str, Any], path_value: str | None = None) -> Path:
    path = config_path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def config_default(config: dict[str, Any], key: str, env_name: str | None = None) -> Any:
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    if key in config:
        return config[key]
    defaults = config.get("defaults", {})
    return defaults.get(key)


def repo_config(config: dict[str, Any], repo: str | None) -> dict[str, Any]:
    repos = config.get("repos") or []
    if repo:
        resolved = str(Path(repo).expanduser())
        for item in repos:
            if str(Path(item.get("path", "")).expanduser()) == resolved:
                return item
    return repos[0] if repos else {}


def env_or_arg(value: str | None, env_name: str, required: bool = True) -> str | None:
    resolved = value or os.environ.get(env_name)
    if required and not resolved:
        raise SystemExit(f"Missing {env_name}. Pass the flag or export {env_name}.")
    return resolved


def value_or_config(value: str | None, config_value: Any, env_name: str, required: bool = True) -> str | None:
    resolved = value or os.environ.get(env_name) or config_value
    if required and not resolved:
        raise SystemExit(f"Missing {env_name}. Pass the flag, export {env_name}, or run configure.")
    return str(resolved) if resolved is not None else None


def build_url(base: str, path: str, query: dict[str, str] | None = None, *, json_suffix: bool = False) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if json_suffix and not normalized.endswith(".json"):
        normalized = f"{normalized}.json"
    url = f"{base.rstrip('/')}{normalized}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


def harvest_url(path: str, query: dict[str, str] | None = None) -> str:
    return build_url(API_BASE, path, query, json_suffix=True)


def docs_harvest_url(path: str, query: dict[str, str] | None = None) -> str:
    return build_url("https://api.harvestapp.com/v2", path, query, json_suffix=False)


def request_json(method: str, url: str, account_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = os.environ.get("HARVEST_ACCESS_TOKEN")
    if not token:
        raise SystemExit("Missing HARVEST_ACCESS_TOKEN. Export a fresh Harvest Personal Access Token before running.")

    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": os.environ.get("HARVEST_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/json",
    }
    if account_id:
        headers["Harvest-Account-Id"] = account_id
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HarvestApiError(method, url, exc.code, detail) from exc


def local_target_date(value: str | None) -> str:
    if value:
        return value
    today = dt.date.today()
    offset = 3 if today.weekday() == 0 else 1
    return (today - dt.timedelta(days=offset)).isoformat()


def git_commits(repo: str, date_value: str) -> list[dict[str, str]]:
    since = f"{date_value} 00:00"
    until = f"{date_value} 23:59:59"
    cmd = [
        "git",
        "-C",
        repo,
        "log",
        "--all",
        f"--since={since}",
        f"--until={until}",
        "--date=local",
        "--pretty=format:%h%x09%s",
    ]
    output = subprocess.check_output(cmd, text=True).strip()
    commits: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        short_hash, _, subject = line.partition("\t")
        commits.append({"hash": short_hash, "subject": subject})
    return commits


def clean_subject(subject: str) -> str:
    for prefix in ("feat", "fix", "docs", "refactor", "test", "chore", "style", "build", "ci", "perf"):
        marker = f"{prefix}("
        if subject.startswith(marker) and "):" in subject:
            return subject.split(":", 1)[1].strip()
        if subject.startswith(prefix + ":"):
            return subject.split(":", 1)[1].strip()
    return subject.strip()


def ensure_note_prefix(note: str, prefix: str | None = None) -> str:
    active_prefix = (prefix if prefix is not None else DEFAULT_NOTE_PREFIX).strip()
    stripped = note.strip()
    if not active_prefix or stripped.startswith(active_prefix):
        return stripped
    return f"{active_prefix} {stripped}"


def generated_note(repo: str, date_value: str, prefix: str | None = None, repo_label: str | None = None) -> str:
    commits = git_commits(repo, date_value)
    label = repo_label or Path(repo).name or "repository"
    if not commits:
        return ensure_note_prefix(f"No commit-backed {label} activity found for this date.", prefix)
    subjects = []
    seen = set()
    for commit in commits:
        subject = clean_subject(commit["subject"])
        key = subject.lower()
        if key not in seen:
            seen.add(key)
            subjects.append(subject)
        if len(subjects) >= 5:
            break
    if len(subjects) == 1:
        work = subjects[0]
    else:
        work = "; ".join(subjects[:-1]) + f"; and {subjects[-1]}"
    return ensure_note_prefix(f"I worked on {label} updates including {work}.", prefix)


def print_assignment_rows(assignments: list[dict[str, Any]]) -> bool:
    if not assignments:
        return False
    for assignment in assignments:
        project = assignment.get("project", {})
        client = assignment.get("client", {})
        print(f"PROJECT {project.get('id')} | {client.get('name', 'No client')} | {project.get('name')} | code={project.get('code') or ''}")
        for task_assignment in assignment.get("task_assignments", []):
            task = task_assignment.get("task", {})
            active = "active" if task_assignment.get("is_active") else "inactive"
            billable = "billable" if task_assignment.get("billable") else "non-billable"
            print(f"  TASK {task.get('id')} | {task.get('name')} | {active}, {billable}")
    return True


def print_time_entry_pairs(entries: list[dict[str, Any]]) -> bool:
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        project = entry.get("project") or {}
        task = entry.get("task") or {}
        project_id = project.get("id")
        task_id = task.get("id")
        if not project_id or not task_id:
            continue
        key = (str(project_id), str(task_id))
        pairs.setdefault(key, {"project": project, "task": task, "latest_date": entry.get("spent_date")})
    if not pairs:
        return False
    print("Project/task pairs found from recent time entries:")
    for (_project_id, _task_id), item in sorted(pairs.items(), key=lambda pair: (pair[1].get("project", {}).get("name") or "", pair[1].get("task", {}).get("name") or "")):
        project = item["project"]
        task = item["task"]
        print(f"PROJECT {project.get('id')} | {project.get('name')}")
        print(f"  TASK {task.get('id')} | {task.get('name')} | seen on {item.get('latest_date')}")
    return True


def print_discovery(account_id: str, user_id: str | None) -> None:
    if not user_id:
        me = request_json("GET", harvest_url("/users/me"), account_id)
        user_id = str(me["id"])
        print(f"Authenticated Harvest user: {me.get('first_name', '')} {me.get('last_name', '')} ({user_id})".strip())

    query = {"per_page": "2000"}
    candidates = [
        harvest_url(f"/users/{user_id}/project_assignments", query),
        docs_harvest_url(f"/users/{user_id}/project_assignments", query),
        harvest_url("/users/me/project_assignments", query),
        docs_harvest_url("/users/me/project_assignments", query),
    ]
    errors: list[str] = []
    for url in candidates:
        try:
            data = request_json("GET", url, account_id)
        except HarvestApiError as exc:
            errors.append(f"{exc.code} {url}")
            continue
        if print_assignment_rows(data.get("project_assignments", [])):
            return

    today = dt.date.today()
    start = today - dt.timedelta(days=120)
    params = {"from": start.isoformat(), "to": today.isoformat(), "per_page": "2000"}
    if user_id:
        params["user_id"] = user_id
    try:
        data = request_json("GET", harvest_url("/time_entries", params), account_id)
    except HarvestApiError as exc:
        attempted = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"Project-assignment discovery failed. Attempted:\n{attempted}\nRecent time-entry fallback also failed: {exc}") from exc

    if print_time_entry_pairs(data.get("time_entries", [])):
        return

    attempted = "\n".join(f"- {error}" for error in errors)
    print(f"Project-assignment discovery returned 404/empty for every variant attempted:\n{attempted}")
    print("No recent time entries with project/task ids were found in the last 120 days. Create one manual Harvest entry for the intended project/task, then rerun discovery, or ask a Harvest admin for the project and task IDs.")


def find_existing(account_id: str, user_id: str | None, project_id: str, task_id: str, date_value: str) -> list[dict[str, Any]]:
    params = {
        "from": date_value,
        "to": date_value,
        "project_id": project_id,
        "task_id": task_id,
        "per_page": "2000",
    }
    if user_id:
        params["user_id"] = user_id
    url = harvest_url("/time_entries", params)
    data = request_json("GET", url, account_id)
    entries = []
    for entry in data.get("time_entries", []):
        if entry.get("spent_date") != date_value:
            continue
        if str(entry.get("project", {}).get("id")) != str(project_id):
            continue
        if str(entry.get("task", {}).get("id")) != str(task_id):
            continue
        if user_id and str(entry.get("user", {}).get("id")) != str(user_id):
            continue
        entries.append(entry)
    return entries


def build_payload(args: argparse.Namespace, date_value: str, notes: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": int(args.project_id),
        "task_id": int(args.task_id),
        "spent_date": date_value,
        "notes": notes,
    }
    if args.user_id:
        payload["user_id"] = int(args.user_id)
    if args.entry_mode == "clock":
        payload["started_time"] = args.started_time
        payload["ended_time"] = args.ended_time
    else:
        payload["hours"] = float(args.hours)
    return payload


def load_notes(args: argparse.Namespace, date_value: str, note_prefix: str | None, repo_label: str | None) -> str:
    if args.notes_file:
        return ensure_note_prefix(Path(args.notes_file).read_text(), note_prefix)
    if args.notes:
        return ensure_note_prefix(args.notes, note_prefix)
    return generated_note(args.repo, date_value, note_prefix, repo_label)


def upsert(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    repo_settings = repo_config(config, args.repo)
    defaults = config.get("defaults", {})
    args.repo = args.repo or repo_settings.get("path") or defaults.get("repo") or DEFAULT_REPO
    account_id = value_or_config(args.account_id, config_default(config, "account_id"), "HARVEST_ACCOUNT_ID")
    args.user_id = value_or_config(args.user_id, config_default(config, "user_id"), "HARVEST_USER_ID", required=False)
    args.project_id = value_or_config(args.project_id, repo_settings.get("project_id") or config_default(config, "project_id"), "HARVEST_PROJECT_ID")
    args.task_id = value_or_config(args.task_id, repo_settings.get("task_id") or config_default(config, "task_id"), "HARVEST_TASK_ID")
    args.started_time = args.started_time or repo_settings.get("started_time") or defaults.get("started_time") or "8:00am"
    args.ended_time = args.ended_time or repo_settings.get("ended_time") or defaults.get("ended_time") or "4:00pm"
    args.hours = args.hours or str(repo_settings.get("hours") or defaults.get("hours") or "8")
    args.entry_mode = args.entry_mode or repo_settings.get("entry_mode") or defaults.get("entry_mode") or os.environ.get("HARVEST_ENTRY_MODE") or "clock"
    note_prefix = args.note_prefix if args.note_prefix is not None else repo_settings.get("note_prefix") or defaults.get("note_prefix") or DEFAULT_NOTE_PREFIX
    repo_label = repo_settings.get("label") or Path(args.repo).name
    date_value = local_target_date(args.date)
    notes = load_notes(args, date_value, note_prefix, repo_label)
    payload = build_payload(args, date_value, notes)
    existing = find_existing(account_id, args.user_id, args.project_id, args.task_id, date_value)

    action = "update" if existing else "create"
    if args.dry_run:
        print(json.dumps({"dry_run": True, "action": action, "date": date_value, "existing_ids": [e.get("id") for e in existing], "payload": payload}, indent=2))
        return

    if existing:
        entry = existing[0]
        if entry.get("is_locked") or entry.get("approval_status") == "approved":
            raise SystemExit(f"Existing entry {entry.get('id')} is locked/approved; not updating automatically.")
        result = request_json("PATCH", harvest_url(f"/time_entries/{entry['id']}"), account_id, payload)
        print(json.dumps({"action": "updated", "id": result.get("id"), "date": date_value}, indent=2))
    else:
        result = request_json("POST", harvest_url("/time_entries"), account_id, payload)
        print(json.dumps({"action": "created", "id": result.get("id"), "date": date_value}, indent=2))


def print_section(title: str, body: str | None = None) -> None:
    print()
    print(f"== {title} ==")
    if body:
        print(body)


def prompt_value(
    label: str,
    default: str | None = None,
    *,
    required: bool = True,
    help_text: str | None = None,
) -> str:
    if help_text:
        print(help_text)
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            print(f"Using default: {default}")
            return default
        if not required:
            print("Leaving blank.")
            return ""
        print("Required. Enter a value to continue.")


def yes_no(label: str, default: bool = False, *, help_text: str | None = None) -> bool:
    if help_text:
        print(help_text)
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        print(f"Using default: {'yes' if default else 'no'}")
        return default
    return value in {"y", "yes"}


def ensure_token_for_setup() -> None:
    if os.environ.get("HARVEST_ACCESS_TOKEN"):
        print("Using HARVEST_ACCESS_TOKEN from your shell for this setup run.")
        return
    print_section(
        "1. Harvest Personal Access Token",
        "Open Harvest's developer page and create a Personal Access Token. "
        "This token lets the setup wizard ask Harvest which projects/tasks you can log time to. "
        "The token is used only for this terminal session and is not written to the config file.",
    )
    print("Harvest developer page:")
    print("https://id.getharvest.com/developers")
    print("Look for the Personal Access Tokens area, create a token, then paste it at the hidden prompt below.")
    token = getpass.getpass("Paste Harvest Personal Access Token for setup only: ").strip()
    if token:
        os.environ["HARVEST_ACCESS_TOKEN"] = token


def collect_assignment_options(account_id: str, user_id: str | None) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    query = {"per_page": "2000"}
    candidates = []
    if user_id:
        candidates.extend([
            harvest_url(f"/users/{user_id}/project_assignments", query),
            docs_harvest_url(f"/users/{user_id}/project_assignments", query),
        ])
    candidates.extend([
        harvest_url("/users/me/project_assignments", query),
        docs_harvest_url("/users/me/project_assignments", query),
    ])
    for url in candidates:
        try:
            data = request_json("GET", url, account_id)
        except HarvestApiError:
            continue
        for assignment in data.get("project_assignments", []):
            project = assignment.get("project") or {}
            for task_assignment in assignment.get("task_assignments", []):
                task = task_assignment.get("task") or {}
                if project.get("id") and task.get("id"):
                    options.append({"project": project, "task": task})
        if options:
            return options
    return options


def print_options(options: list[dict[str, Any]]) -> None:
    for index, option in enumerate(options, 1):
        project = option["project"]
        task = option["task"]
        print(f"{index}. PROJECT {project.get('id')} | {project.get('name')} -> TASK {task.get('id')} | {task.get('name')}")


def choose_option(options: list[dict[str, Any]], prompt: str) -> dict[str, Any] | None:
    if not options:
        return None
    print_options(options)
    while True:
        raw = input(f"{prompt} [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Choose one of the listed numbers.")


def configure(args: argparse.Namespace) -> None:
    print("Harvest Timekeeper first-run setup")
    print("This wizard creates a local, non-secret config file for Harvest time entries.")
    print("It does not save your Harvest token. It only saves IDs, repo paths, note preferences, and time-entry defaults.")

    ensure_token_for_setup()
    existing = load_config(args.config)

    print_section(
        "2. Harvest Account and User",
        "Harvest accounts contain projects and time entries. Your user id identifies whose time entries will be created. "
        "If the token can read your profile, the wizard detects the user id automatically.",
    )
    account_default = str(config_default(existing, "account_id") or os.environ.get("HARVEST_ACCOUNT_ID") or "") or None
    account_id = prompt_value(
        "Harvest account id",
        account_default,
        help_text="Use the account id shown by Harvest. If Codex helped you test earlier, this may already be in the command output.",
    )
    user_default = str(config_default(existing, "user_id") or os.environ.get("HARVEST_USER_ID") or "") or None
    if user_default:
        user_id = prompt_value("Harvest user id", user_default)
    else:
        try:
            me = request_json("GET", harvest_url("/users/me"), account_id)
            user_id = str(me["id"])
            print(f"Detected Harvest user id: {user_id}")
        except HarvestApiError:
            user_id = prompt_value(
                "Harvest user id",
                help_text="The wizard could not detect your user id automatically. Enter the id returned by Harvest's users/me endpoint.",
            )

    print_section(
        "3. Default Harvest Project and Task",
        "A Harvest project is usually the client/project bucket. A task is the billing/work category inside that project. "
        "Choose the project/task that should be used by default when Codex writes your daily entry.",
    )
    options = collect_assignment_options(account_id, user_id)
    if options:
        selected = choose_option(options, "Default project/task for time entries")
        project_id = str(selected["project"]["id"])
        task_id = str(selected["task"]["id"])
        print(f"Using PROJECT {project_id} and TASK {task_id} as the default mapping.")
    else:
        print("Could not list project assignments. You can still enter ids manually.")
        print("If you do not know them, create one manual Harvest entry for the intended project/task, rerun discovery, or ask a Harvest admin.")
        project_id = prompt_value("Default project id", str(config_default(existing, "project_id") or "") or None)
        task_id = prompt_value("Default task id", str(config_default(existing, "task_id") or "") or None)

    print_section(
        "4. Git Repository and Note Label",
        "Codex writes notes from git commits. The repo path tells the helper where to run `git log --all`. "
        "The short label appears in generated notes, so choose something a human would recognize.",
    )
    repo_default = str((existing.get("repos") or [{}])[0].get("path") or config_default(existing, "repo") or DEFAULT_REPO)
    repo_path = prompt_value("Repo path to summarize", repo_default)
    label_default = str((existing.get("repos") or [{}])[0].get("label") or Path(repo_path).name)
    repo_label = prompt_value("Short repo/work label for generated notes", label_default)

    print_section(
        "5. Note Prefix and Time Defaults",
        "The note prefix is optional text placed at the beginning of each Harvest note for sorting, for example `[PRODUCT]`. "
        "Clock mode sends a start and end time, while duration mode sends only the number of hours. Most users should keep clock mode unless Harvest rejects it.",
    )
    prefix_default = str(config_default(existing, "note_prefix") or DEFAULT_NOTE_PREFIX)
    note_prefix = prompt_value("Note prefix to prepend, blank allowed", prefix_default, required=False)
    started_time = prompt_value("Start time", str(config_default(existing, "started_time") or "8:00am"))
    ended_time = prompt_value("End time", str(config_default(existing, "ended_time") or "4:00pm"))
    hours = prompt_value("Hours", str(config_default(existing, "hours") or "8"))
    entry_mode = prompt_value("Entry mode: clock or duration", str(config_default(existing, "entry_mode") or "clock"))

    repos = [{
        "path": repo_path,
        "label": repo_label,
        "project_id": project_id,
        "task_id": task_id,
        "note_prefix": note_prefix,
        "started_time": started_time,
        "ended_time": ended_time,
        "hours": hours,
        "entry_mode": entry_mode,
    }]

    print_section(
        "6. Optional Additional Repo Mappings",
        "Use this only if you want different repositories to log to different Harvest project/task pairs. "
        "For example, one repo could map to a client project while another maps to internal product work.",
    )
    while yes_no("Add another repo/project/task mapping?", False):
        extra_repo = prompt_value("Repo path")
        extra_label = prompt_value("Short label", Path(extra_repo).name)
        if options:
            selected = choose_option(options, f"Project/task for {extra_label}")
            extra_project = str(selected["project"]["id"])
            extra_task = str(selected["task"]["id"])
        else:
            extra_project = prompt_value("Project id")
            extra_task = prompt_value("Task id")
        extra_prefix = prompt_value("Note prefix for this repo, blank allowed", f"[{extra_label.upper()}]", required=False)
        repos.append({
            "path": extra_repo,
            "label": extra_label,
            "project_id": extra_project,
            "task_id": extra_task,
            "note_prefix": extra_prefix,
            "started_time": started_time,
            "ended_time": ended_time,
            "hours": hours,
            "entry_mode": entry_mode,
        })

    print_section(
        "7. Optional Commit Keyword Routing",
        "Keyword rules are saved for Codex/automation guidance. They are useful if some commits should be considered for a different project/task, "
        "but this script does not automatically split one day into multiple Harvest entries yet.",
    )
    commit_rules = []
    if yes_no("Add keyword rules to route certain commits to different project/tasks later?", False):
        while True:
            keyword = prompt_value("Commit subject keyword or phrase", required=False)
            if not keyword:
                break
            if options:
                selected = choose_option(options, f"Project/task for commits matching {keyword}")
                rule_project = str(selected["project"]["id"])
                rule_task = str(selected["task"]["id"])
            else:
                rule_project = prompt_value("Project id")
                rule_task = prompt_value("Task id")
            commit_rules.append({"match": keyword, "project_id": rule_project, "task_id": rule_task})
            if not yes_no("Add another keyword rule?", False):
                break

    config = {
        "version": 1,
        "account_id": account_id,
        "user_id": user_id,
        "defaults": {
            "project_id": project_id,
            "task_id": task_id,
            "note_prefix": note_prefix,
            "started_time": started_time,
            "ended_time": ended_time,
            "hours": hours,
            "entry_mode": entry_mode,
            "repo": repo_path,
        },
        "repos": repos,
        "commit_rules": commit_rules,
    }
    path = save_config(config, args.config)

    helper = "python3 ~/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py"
    print_section("Setup Complete")
    print(f"Saved non-secret config: {path}")
    print("Next, verify without writing to Harvest:")
    print(f"  {helper} upsert --dry-run --date <YYYY-MM-DD>")
    print("Example for yesterday's entry, letting the helper choose the previous workday:")
    print(f"  {helper} upsert --dry-run")
    print("If the dry run looks right, either:")
    print("  1. Go back to Codex and say: I finished Harvest Timekeeper setup. Please dry-run yesterday's Harvest entry from my commits.")
    print("  2. Or write directly by rerunning the same command without --dry-run.")
    print("Keep HARVEST_ACCESS_TOKEN available in the shell or Codex environment whenever you want to read/write Harvest.")


def normalized_argv() -> list[str]:
    # Ignore whitespace-only arguments produced by accidental `\   --flag` shell input.
    return [arg for arg in sys.argv[1:] if arg.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover Harvest ids and upsert git-backed time entries.")
    sub = parser.add_subparsers(dest="command", required=True)

    configure_parser = sub.add_parser("configure", help="Walk through first-run Harvest setup and write a non-secret config file.")
    configure_parser.add_argument("--config", default=None)

    discover = sub.add_parser("discover", help="List the authenticated user's assigned Harvest projects and tasks.")
    discover.add_argument("--account-id", default=os.environ.get("HARVEST_ACCOUNT_ID"))
    discover.add_argument("--user-id", default=os.environ.get("HARVEST_USER_ID"))

    note = sub.add_parser("note", help="Generate a simple commit-backed note for a date.")
    note.add_argument("--repo", default=None)
    note.add_argument("--date", default=None)
    note.add_argument("--note-prefix", default=None)
    note.add_argument("--config", default=None)

    up = sub.add_parser("upsert", help="Create or update one Harvest time entry.")
    up.add_argument("--account-id", default=os.environ.get("HARVEST_ACCOUNT_ID"))
    up.add_argument("--user-id", default=os.environ.get("HARVEST_USER_ID"))
    up.add_argument("--project-id", default=os.environ.get("HARVEST_PROJECT_ID"))
    up.add_argument("--task-id", default=os.environ.get("HARVEST_TASK_ID"))
    up.add_argument("--date", default=None, help="YYYY-MM-DD. Defaults to previous weekday.")
    up.add_argument("--hours", default=None)
    up.add_argument("--started-time", default=None)
    up.add_argument("--ended-time", default=None)
    up.add_argument("--entry-mode", choices=["clock", "duration"], default=None)
    up.add_argument("--note-prefix", default=None)
    up.add_argument("--config", default=None)
    up.add_argument("--notes", default=None)
    up.add_argument("--notes-file", default=None)
    up.add_argument("--repo", default=None)
    up.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(normalized_argv())
    try:
        if args.command == "configure":
            configure(args)
        elif args.command == "discover":
            account_id = env_or_arg(args.account_id, "HARVEST_ACCOUNT_ID")
            print_discovery(account_id, args.user_id)
        elif args.command == "note":
            config = load_config(args.config)
            settings = repo_config(config, args.repo)
            repo_path = args.repo or settings.get("path") or config_default(config, "repo") or DEFAULT_REPO
            date_value = local_target_date(args.date)
            note_prefix = args.note_prefix if args.note_prefix is not None else settings.get("note_prefix") or config_default(config, "note_prefix") or DEFAULT_NOTE_PREFIX
            repo_label = settings.get("label") or Path(repo_path).name
            print(generated_note(repo_path, date_value, note_prefix, repo_label))
        elif args.command == "upsert":
            upsert(args)
    except HarvestApiError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
