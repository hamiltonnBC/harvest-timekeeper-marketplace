---
name: harvest-timesheet
description: Generate and write Harvest time entries from git-backed work evidence. Use when the user wants Codex to configure, create, update, dry-run, or automate Harvest time tracker entries based on commits with concise professional notes.
---

# Harvest Timesheet

## Purpose

Create or update Harvest time entries from commit-backed work summaries. Keep the Harvest API token out of prompts, files, git, and shared plugin content. Use `HARVEST_ACCESS_TOKEN` from the shell environment or the local setup wizard only.

## First-Run Setup

When a user starts with this plugin, first direct them to Harvest's developer page:

https://id.getharvest.com/developers

Tell them to create a fresh Personal Access Token and keep it out of chat, git, plugin files, and automation prompts. They need their own token because Harvest time entries are user-specific. They also need their own account id and user id; project/task ids can differ by user because Harvest assignments differ per person.

The easiest shared setup path is for the user to run the interactive configuration wizard in their own visible terminal. Do not run `configure` inside a Codex tool terminal unless the user explicitly says they can type into that terminal, because the wizard may prompt for a Harvest token. The wizard explains each setup concept as it goes: Personal Access Token, account/user ids, project/task selection, repo path, note label, note prefix, work times, repo mappings, and optional keyword routing notes. It writes non-secret settings to `~/.config/harvest-timekeeper/config.json` and never saves the token.

Give the user this command to run themselves:

```bash
python3 ~/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py configure
```

## Share-Safe Defaults

- No Harvest account id, user id, project id, task id, repo path, email, or note prefix is stored in the shared plugin.
- Personal settings belong in `~/.config/harvest-timekeeper/config.json` or environment variables.
- Tokens must stay in `HARVEST_ACCESS_TOKEN` or be typed into the local setup wizard for that run only.
- Default entry behavior is configurable; the wizard asks for start time, end time, hours, and entry mode.

## Workflow

1. For a new user, direct them to run `configure` first in their own visible terminal. Do not launch the wizard in Codex's background/tool terminal by default. Confirm `HARVEST_ACCESS_TOKEN` is available in the user's shell or let the local terminal wizard prompt for it without saving it. Do not ask the user to paste a token into chat.
2. If project/task ids are unknown and the user does not want the full wizard, run discovery. Use the user's own account id and user id:

```bash
export HARVEST_ACCESS_TOKEN='fresh-token-from-harvest'

python3 ~/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py discover \
  --account-id <ACCOUNT_ID> \
  --user-id <USER_ID>
```

3. For the target date, gather commit evidence from the configured repo or the repo the user passes with `--repo`:

```bash
git -C <REPO_PATH> log --all \
  --since='<YYYY-MM-DD 00:00>' \
  --until='<YYYY-MM-DD 23:59:59>' \
  --date=local \
  --pretty=format:'%h %s'
```

If a worktree or branch-local view looks empty, use `git log --all` in the configured shared checkout before saying there was no activity.

4. Write a concise first-person Harvest note. If the user configured a prefix, the helper prepends it automatically. Use only commit-backed evidence. Group related commits into one coherent note. Avoid speculation about meetings, motives, or future work.
5. Dry-run before first real write. After `configure`, flags such as account/user/project/task/repo/times can be omitted because they come from config:

```bash
python3 ~/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py upsert \
  --dry-run \
  --date <YYYY-MM-DD>
```

6. After the wizard finishes, tell the user to come back to Codex and say: `I finished Harvest Timekeeper setup. Please dry-run yesterday's Harvest entry from my commits.`
7. Write the entry after the dry-run looks right by removing `--dry-run`, or let Codex do that final write after reviewing the dry-run payload.

## Daily Automation Behavior

For a weekday morning automation, target the previous local calendar day. For Monday, target the previous Friday unless the user asks for weekend entries.

Use one Harvest entry per date/project/task. The script lists matching entries first, then patches the first match instead of creating a duplicate. If no match exists, it creates a new entry.

The config file can store multiple repo-to-project/task mappings and optional commit keyword routing notes. Current script upserts one selected repo/date at a time; Codex automation should use the config mappings to decide which repo/project/task entry to write. Keyword rules are saved as guidance for Codex and future automation refinement, not automatic commit splitting yet.

Use `--entry-mode clock` for start/end-time entries. If Harvest rejects clock-style entries because the account tracks duration only, rerun with `--entry-mode duration`, which sends `hours` instead.

## Shell Command Formatting

For multiline commands, the `\` must be the final character on the line. If the shell shows `unrecognized arguments:` after a command copied with backslashes, rerun it as a single line:

```bash
python3 ~/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py discover --account-id <ACCOUNT_ID> --user-id <USER_ID>
```

## References

Read `references/harvest-api.md` when you need endpoint details, first-run setup guidance, required env vars, or troubleshooting guidance.
