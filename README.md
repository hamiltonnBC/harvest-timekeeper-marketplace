# Harvest Timekeeper Marketplace

Harvest Timekeeper is a local Codex marketplace bundle for creating Harvest time entries from git-backed work summaries. It helps Codex turn commits into concise Harvest notes, then create or update time entries without duplicating existing rows.

## What It Does

- Guides each user through Harvest setup with a local configuration wizard.
- Uses a Harvest Personal Access Token only for the current terminal session; tokens are not saved.
- Discovers Harvest projects and tasks assigned to the user.
- Saves non-secret preferences in `~/.config/harvest-timekeeper/config.json`.
- Creates or updates Harvest entries for a date/project/task instead of blindly duplicating entries.
- Generates notes from `git log --all` evidence for the configured repo.
- Supports an optional note prefix such as `[PRODUCT]` or `[CLIENT-A]` for easier Harvest sorting.
- Supports one or more repo-to-Harvest project/task mappings.
- Stores optional commit keyword routing rules as guidance for Codex and future automation refinement.
- Supports clock-style entries with start/end time, or duration-style entries with hours only.

## Current Limits

- The helper upserts one repo/date/project/task entry at a time.
- Keyword routing is saved as guidance for Codex. It does not automatically split one day of commits into multiple Harvest entries yet.
- Users must keep `HARVEST_ACCESS_TOKEN` available when reading from or writing to Harvest.

## Install From GitHub

Clone the marketplace bundle. If your environment supports the owner/repo shorthand you provided, use:

```bash
mkdir -p ~/plugins
cd ~/plugins
git clone hamiltonnBC/harvest-timekeeper-marketplace.git
```

If your Git client expects a full GitHub URL, use:

```bash
mkdir -p ~/plugins
cd ~/plugins
git clone https://github.com/hamiltonnBC/harvest-timekeeper-marketplace.git
```

Then install the local marketplace and plugin:

```bash
codex plugin marketplace add ~/plugins/harvest-timekeeper-marketplace
codex plugin add harvest-timekeeper@harvest-timekeeper
```

Start a new Codex chat and say:

```text
Use $harvest-timesheet to configure Harvest and write yesterday's time entry.
```

## First-Time Configuration

Codex should tell you to run the configuration wizard in your own visible terminal. Run:

```bash
python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py configure
```

The wizard will walk you through:

- opening Harvest's developer page: https://id.getharvest.com/developers
- creating a Harvest Personal Access Token
- entering your Harvest account id
- detecting or entering your Harvest user id
- selecting your default Harvest project/task
- choosing the git repo to summarize
- choosing a short repo/work label for generated notes
- choosing an optional note prefix
- choosing start time, end time, hours, and entry mode
- adding optional repo-to-project/task mappings
- adding optional commit keyword routing rules

The wizard saves non-secret settings to:

```bash
~/.config/harvest-timekeeper/config.json
```

It does not save your Harvest token.

## Verify Before Writing

After configuration, dry-run an entry before writing to Harvest:

```bash
python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py upsert --dry-run --date <YYYY-MM-DD>
```

Or let the helper choose the previous workday:

```bash
python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py upsert --dry-run
```

If the dry run looks right, go back to Codex and say:

```text
I finished Harvest Timekeeper setup. Please dry-run yesterday's Harvest entry from my commits.
```

After reviewing the dry run, Codex can write the entry, or you can run the same command without `--dry-run`.

## Repo and Project Mapping

During setup, you can map one repo to one Harvest project/task, or add additional mappings. For example:

- `~/work/client-app` -> Client project / Development task
- `~/work/internal-tooling` -> Internal project / Product task
- `~/work/research` -> Internal project / Research task

The config stores these mappings so Codex can choose the right Harvest destination for future entries.

## Commit Keyword Routing

The wizard can save rules such as:

```json
{
  "match": "qa",
  "project_id": "<project id>",
  "task_id": "<task id>"
}
```

These are currently guidance for Codex and automation prompts. They are useful when certain commit themes should be considered for different Harvest projects or tasks, but automatic multi-entry splitting is not implemented yet.

## Security Notes

- Do not commit `~/.config/harvest-timekeeper/config.json` unless you intentionally want to share non-secret IDs and repo paths.
- Never commit or paste Harvest Personal Access Tokens.
- If a token appears in chat, shell history, or logs, revoke it and create a fresh one.
- This marketplace bundle should not contain user-specific Harvest IDs, repo paths, note prefixes, or tokens.
