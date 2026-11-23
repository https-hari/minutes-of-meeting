# Security and privacy

## Reporting a vulnerability

Please don't open a public issue. Use **Security → Report a vulnerability** on this repository
(<https://github.com/https-hari/minutes-of-meeting/security/advisories/new>). You'll get a reply within 7 days.

## How data is protected

- **Login:** the website uses Supabase Auth; the API verifies each request's token and uses its user id.
- **Isolation:** every query is filtered by the signed-in user. Another user's meeting, task or memory id
  returns 404. This is covered by automated tests.
- **Data leaves only to:** your database (Supabase/Postgres) and Groq (transcription, extraction, answers).
  No analytics or third-party tracking.
- **Extension:** captures only after you click Start, shows a visible "taking notes" badge, sends only to the
  server you approved, and keeps an unsent copy locally until it uploads.
- **Recording consent:** tell participants you're taking notes; recording without consent is illegal in
  many places.

## Keys

- Server secrets (`DATABASE_URL`, `GROQ_API_KEY`) live only in `backend/.env` locally and in the host's
  secret settings in production. `.env` files are git-ignored; `.env.example` files stay blank.
- The website only receives the Supabase URL and the **publishable/anon** key. Never use the service-role key.
- If a secret was ever committed or shared, rotate it at the provider; deleting the commit is not enough.
