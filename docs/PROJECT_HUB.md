# Audiotheca Project Hub

The project hub is a small, read-only local site modeled on the Oneirodex project board. It gives this repository a landing page for project status, roadmap, quality/security notes, documentation, and recent changes.

## Start it

From the Audiotheca repository root, run either:

```powershell
.\start-project-hub.cmd
```

or:

```powershell
python start-project-hub.py
```

Then open <http://127.0.0.1:6129/>. Press **Ctrl+C** in the terminal to stop the server. The hub uses only Python's standard library; it does not need Codex, Node, the Audiotheca API, or a running scan.

## What it serves

- Fixed HTML/CSS/JavaScript pages under `project_hub/site/`.
- A small `/api/status` response with the current Git branch, commit, and count of changed files. It does not return filenames.
- An explicit allowlist of project Markdown documents under `/source/`.

The server binds to `127.0.0.1`, is read-only, and does not load `.env`, API tokens, scan reports, or library contents. It is intended for local use, not LAN hosting. Port 6129 must be free.

## Pages

- **Project hub** — repository status and page navigation.
- **Roadmap** — recorded delivery status and links to source plans.
- **Quality & security** — safety boundaries and recorded validation evidence.
- **Documentation** — local links to operator and engineering guides.
- **Recent changes** — summary of the current Unreleased changelog section.

The hub defaults to dark mode and stores an optional theme choice in the browser's local storage.
