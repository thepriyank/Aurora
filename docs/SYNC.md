# SYNC.md — one memory on every device (Phase 3)

The assistant's memory is a folder of plain markdown (the **vault**). No
database, no lock files. That's the whole reason this works: any file-sync tool
can carry it, and `git` gives you history for free.

```
<vault>/
  01 - Daily Notes/     2026-09-04.laptop.md   (per-device shard)
                        2026-09-04.md          (merged nightly)
  04 - Sessions/        <same shard pattern>
  People/  Projects/    People/Me.md, Projects/Notes.md, …
  VAULT-INDEX.md        profile + "read these notes first" sets
  .git/                 30-min snapshots (scripts/vault_commit.py)
```

The vault location lives in `config/jarvis.json` → `vault_path`. The first-run
wizard (`python -m jarvis_brain configure`) asks for it and scaffolds the
folders. `device_name` in the same file labels this machine's shards.

---

## 1. Google Drive for desktop

### Windows
1. Install **Google Drive for desktop** — <https://google.com/drive/download>.
2. Sign in. It mounts as a drive (usually `G:`) and mirrors `My Drive` under
   `C:\Users\<you>\My Drive`.
3. Put the vault at e.g. `C:\Users\<you>\My Drive\Jarvis Vault`.
4. Right-click the folder → **Offline access → Available offline** (so the
   assistant never blocks on a download).
5. Set it in `config/jarvis.json`:
   `"vault_path": "~/My Drive/Jarvis Vault"`.

### macOS
1. Install Google Drive for desktop, sign in.
2. It appears at
   `~/Library/CloudStorage/GoogleDrive-<email>/My Drive`.
3. Put the vault at `.../My Drive/Jarvis Vault`, mark it **available offline**.
4. `"vault_path": "~/Library/CloudStorage/GoogleDrive-<email>/My Drive/Jarvis Vault"`.

> iCloud Drive or Dropbox work identically — point `vault_path` at a folder
> inside their sync root.

---

## 2. Android

Pick **one**:

| Option | Cost | Notes |
|---|---|---|
| **Autosync for Google Drive** (or *DriveSync*, *FolderSync*) | free / small | Point it at the Drive `Jarvis Vault` folder ↔ a local folder Obsidian opens. Two-way, ~every 15 min. |
| **Obsidian Sync** | $4–8/mo | Simplest and most reliable on mobile. Skips Drive entirely — Obsidian syncs its own way. If you use this, the desktop can still keep Drive + git as a backup. |

Either way: install **Obsidian** from the Play Store and open the synced
folder as a vault.

---

## 3. Exclude the churn

These files change every time you move the cursor and cause almost all false
conflicts. `scripts/vault_commit.py` writes them into the vault's `.gitignore`
on first run:

```
.obsidian/workspace.json
.obsidian/workspace*.json
.obsidian/cache
.trash/
.DS_Store
```

In your sync app, also add `.obsidian/workspace*.json` and `.trash/` to its
**exclude / ignore** list if it supports one (Autosync and FolderSync do).

---

## 4. Same-day edits never conflict — per-device shards

Each device writes its own file: `2026-09-04.laptop.md`,
`2026-09-04.phone.md`. Two devices editing "today" touch **different files**,
so the sync has nothing to merge.

`scripts/vault_consolidate.py` runs nightly and folds the day's shards into a
single `2026-09-04.md` under `## laptop` / `## phone` headings, then deletes the
shards. It's idempotent — a shard that syncs in late is picked up on the next
run.

---

## 5. History = git (30-minute snapshots)

`scripts/vault_commit.py`:
- `git init`s the vault on first run (branch `main`) and writes its `.gitignore`
- commits only when something changed
- `--push` also pushes to `origin` if you added one:
  `git -C "<vault>" remote add origin <private-repo-url>`

These scripts are **stdlib-only** — schedule them with a bare `python`, no venv.

### Windows — Task Scheduler
```powershell
# 30-min snapshot
schtasks /create /tn "JarvisVaultCommit" /sc minute /mo 30 ^
  /tr "python \"%USERPROFILE%\path\to\Jarvis\scripts\vault_commit.py\""

# nightly consolidation at 03:10
schtasks /create /tn "JarvisVaultConsolidate" /sc daily /st 03:10 ^
  /tr "python \"%USERPROFILE%\path\to\Jarvis\scripts\vault_consolidate.py\""
```

### macOS — launchd
`~/Library/LaunchAgents/com.jarvis.vaultcommit.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jarvis.vaultcommit</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/you/path/to/Jarvis/scripts/vault_commit.py</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
</dict></plist>
```
```bash
launchctl load ~/Library/LaunchAgents/com.jarvis.vaultcommit.plist
```
Add a second agent for `vault_consolidate.py` with
`StartCalendarInterval` at `Hour 3, Minute 10`.

### Linux — cron
```cron
*/30 * * * *  /usr/bin/python3 /home/you/path/to/Jarvis/scripts/vault_commit.py
10 3   * * *  /usr/bin/python3 /home/you/path/to/Jarvis/scripts/vault_consolidate.py
```

---

## 6. Restore

```bash
cd "<vault>"
git log --oneline                      # find the snapshot
git checkout <sha> -- "People/Me.md"   # one note back
git restore --source <sha> -- .        # everything back (keeps newer as unstaged)
git reset --hard <sha>                 # hard rewind, lose everything after
```

Deleted a note? `git checkout HEAD~1 -- "path/to/Note.md"`.

---

## 7. Checklist

- [ ] Drive for desktop installed on every computer, vault folder **offline**
- [ ] `vault_path` (and `device_name`) set in `config/jarvis.json` on each machine
- [ ] `vault_commit.py` scheduled every 30 min
- [ ] `vault_consolidate.py` scheduled nightly
- [ ] Android: sync app pointed at the folder, or Obsidian Sync paid for
- [ ] `.obsidian/workspace*.json` + `.trash/` excluded in the sync app
- [ ] One test: add a fact on the laptop, wait for sync, see it on the phone
