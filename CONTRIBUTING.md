# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Setup

See **Running locally** in the [README](README.md): backend (`backend/`), website (`web/`), extension (`extension/`).

## Before you open a pull request

- [ ] `cd backend && python -m pytest -q` passes (needs `TEST_DATABASE_URL` to an empty Postgres with pgvector)
- [ ] `cd web && npm run build` passes
- [ ] `node --check` passes for the extension files you changed
- [ ] New routes/tools only return the signed-in user's data, with a test proving it
- [ ] Schema changes have an idempotent upgrade in `backend/app/db/init_db.py`
- [ ] No keys, `.env` files or real meeting data in the diff
- [ ] README / docs updated if setup or behaviour changed

## Most wanted

- **Google Meet changed its captions layout** and the extension captures nothing: update `findRegion()` /
  `readBlocks()` in `extension/content/meet.js`.
- Zoom / Microsoft Teams caption support (a new content script, same `/meetings/live` endpoint).
- More eval questions in `backend/eval/` from real (anonymised) meetings.

## Style

Python with type hints and short functions; TypeScript strict mode; comments explain *why*.
Commit messages: short imperative subject (`Fix caption capture after Meet update`).

By contributing you agree your work is released under the [MIT License](LICENSE) and follows the
[Code of Conduct](CODE_OF_CONDUCT.md).
