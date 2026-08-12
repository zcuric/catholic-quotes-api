# Catholic Quotes API

Standalone Vercel repository for a cited, English-language Catholic quote API.
The repository is intentionally isolated from the Croatian scraper output in
the original data project.

## Deploy

Create a Vercel project from this repository. The repository root is already
the deployable project: Vercel will discover `api/index.py` as a Python
Function and serve `index.html` as the companion browser interface.

For local browsing, do not double-click `index.html` (that creates a `file://`
page with no `/api` origin). Run:

```bash
python3 local_server.py
```

Then open `http://127.0.0.1:8787`.

The database is read-only and contains only:

- 1,345 English Wikiquote author quotations
- 4,858 English Catena canonical-text units

It contains no Croatian JSON, HKM source, or Compendium `content.sqlite`.

## Routes

- `/docs` — human-readable API documentation
- `/api/health`
- `/api/docs`
- `/api/sources`
- `/api/saints`
- `/api/quotes?source=all&q=mercy&limit=25`
- `/api/random?source=wikiquote`

When the source corpus changes, regenerate the snapshot with the
`build_international_sqlite.py` script in the original data project, then
replace the checked-in `data/international.sqlite3`. Deployment does not
depend on the source project or on a build-time database download.
