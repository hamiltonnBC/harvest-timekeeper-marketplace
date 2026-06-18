# Harvest API Notes

Use a Harvest Personal Access Token for personal automation. OAuth2 is for integrations where other users authenticate into an app.

## First-Run Setup

1. Tell the user to run the interactive wizard in their own visible terminal, not inside a Codex background/tool terminal by default:

```bash
python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py configure
```

2. The wizard first sends the user to https://id.getharvest.com/developers for a Personal Access Token.
3. The wizard explains and asks for account/user ids, discovers project/task options, asks for repo path, note label, note prefix, repo mappings, optional keyword routing, and work times.
4. It writes non-secret settings to `~/.config/harvest-timekeeper/config.json`. It does not save the token.
5. After the wizard finishes, the user should return to Codex and ask for a dry-run of yesterday's entry, or run `python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py upsert --dry-run` themselves.

## Manual Discovery Alternative

1. Open https://id.getharvest.com/developers
2. Create a fresh Personal Access Token.
3. Export it locally as `HARVEST_ACCESS_TOKEN`; do not paste it into chat or commit it.
4. Use the account id shown by Harvest, then confirm the user id with `/v2/users/me` if needed.
5. Run discovery to list that user's assigned projects and tasks:

```bash
python3 ~/plugins/harvest-timekeeper-marketplace/plugins/harvest-timekeeper/scripts/harvest_timekeeper.py discover --account-id <ACCOUNT_ID> --user-id <USER_ID>
```

The selected `PROJECT` id and `TASK` id are per-user/per-assignment. Each user should run discovery with their own token and pick from their own assigned list. If Harvest returns 404 for project assignments, the helper falls back to recent time entries and prints project/task pairs found there. If that is empty, create one manual Harvest time entry for the intended project/task and rerun discovery, or ask a Harvest admin for the IDs.

## Environment

Required:

```bash
export HARVEST_ACCESS_TOKEN='fresh-token-from-harvest'
```

Optional overrides:

```bash
export HARVEST_ACCOUNT_ID='<account id from Harvest>'
export HARVEST_USER_ID='<user id from /v2/users/me>'
export HARVEST_PROJECT_ID='<project id from discovery>'
export HARVEST_TASK_ID='<task id from discovery>'
export HARVEST_TIMEKEEPER_CONFIG='~/.config/harvest-timekeeper/config.json'
```

## Endpoints

The helper defaults to `https://api.harvestapp.com/api/v2` and appends `.json`; override with `HARVEST_API_BASE` only if needed.

- `GET https://id.getharvest.com/api/v2/accounts` lists accessible account ids.
- `GET https://api.harvestapp.com/api/v2/users/me.json` confirms the authenticated user.
- `GET https://api.harvestapp.com/api/v2/users/{USER_ID}/project_assignments.json` lists projects and task ids assigned to the user when Harvest permits it.
- `GET https://api.harvestapp.com/api/v2/time_entries.json?from=YYYY-MM-DD&to=YYYY-MM-DD&user_id=...&project_id=...&task_id=...` finds existing entries.
- `POST https://api.harvestapp.com/api/v2/time_entries.json` creates an entry.
- `PATCH https://api.harvestapp.com/api/v2/time_entries/{TIME_ENTRY_ID}.json` updates an entry.

Headers:

```text
Authorization: Bearer $HARVEST_ACCESS_TOKEN
Harvest-Account-Id: $HARVEST_ACCOUNT_ID
User-Agent: Codex Harvest Timekeeper
Content-Type: application/json
```

Do not store access tokens in plugin files, automation prompts, memory, or git. If a token appears in chat or logs, treat it as exposed and rotate it before enabling writes.

## Config File Schema

```json
{
  "version": 1,
  "account_id": "<account id>",
  "user_id": "<user id>",
  "defaults": {
    "project_id": "<project id>",
    "task_id": "<task id>",
    "note_prefix": "[OPTIONAL-PREFIX]",
    "started_time": "8:00am",
    "ended_time": "4:00pm",
    "hours": "8",
    "entry_mode": "clock",
    "repo": "/path/to/repo"
  },
  "repos": [
    {
      "path": "/path/to/repo",
      "label": "repo-label",
      "project_id": "<project id>",
      "task_id": "<task id>",
      "note_prefix": "[OPTIONAL-PREFIX]"
    }
  ],
  "commit_rules": [
    {
      "match": "keyword or phrase",
      "project_id": "<project id>",
      "task_id": "<task id>"
    }
  ]
}
```

`commit_rules` are currently guidance for Codex/automation prompts. They do not automatically split one day's commits into multiple Harvest entries yet.
