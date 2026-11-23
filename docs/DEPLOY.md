# Deploying Minutes

Three free services, about 30 minutes in total. No credit card needed for any of them.

| Part | Where | Why |
|---|---|---|
| Database + login | **Supabase** | Postgres with pgvector, and email / Google sign-in |
| Backend (FastAPI) | **Render** (free web service) | No card needed. The models run on ONNX (fastembed), so the API uses ~300 MB and fits the free 512 MB |
| Website (Next.js) | **Vercel** | Free, deploys from GitHub on every push |

Order matters: Supabase → backend → website → back to Supabase for redirect URLs → extension.

---

## 1. Supabase (database + login)

1. Go to <https://supabase.com> → **New project**. Pick a region close to you (Mumbai: `ap-south-1`).
   Save the **database password** somewhere safe.
2. **Turn on pgvector:** *Database → Extensions* → search `vector` → enable.
   (The backend also tries this on start, but enabling it here avoids permission surprises.)
3. **Get the database URL:** click **Connect** (top bar) → *Connection string* → **Session pooler**
   (not "Direct connection": that one is IPv6-only and won't work from Render). It looks like:
   `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`
   Replace `[YOUR-PASSWORD]`. This is `DATABASE_URL`.
4. **Get the API keys:** *Project Settings → API Keys* (or *Data API*):
   - **Project URL** (`https://abcdefgh.supabase.co`) → `SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL`
   - **anon / publishable key** → `NEXT_PUBLIC_SUPABASE_ANON_KEY` (safe to put in the website)
   - Never put the **service_role / secret** key anywhere in this project.
5. **Email sign-in:** *Authentication → Sign In / Providers → Email* is on by default.
   Supabase's built-in mailer only sends a few emails per hour. For a demo, turn **off**
   "Confirm email" so new accounts can sign in immediately.
6. **Google sign-in (optional):**
   - In <https://console.cloud.google.com>: create a project → *APIs & Services → OAuth consent screen*
     (External, add your email as a test user) → *Credentials → Create credentials → OAuth client ID*
     → type **Web application**.
   - Authorized redirect URI: the **Callback URL** shown in Supabase under
     *Authentication → Sign In / Providers → Google* (`https://abcdefgh.supabase.co/auth/v1/callback`).
   - Paste the Google **Client ID** and **Client secret** into that Supabase Google provider and enable it.
7. URL configuration comes in step 4, once you know the website's address.

## 2. Backend on Render

1. Make sure the code is on GitHub `main` (Render deploys from it, again on every push).
2. <https://render.com> → sign up with GitHub (no card needed for the free plan).
3. **New → Blueprint** → choose the `minutes-of-meeting` repo. Render reads `render.yaml` at the repo
   root (backend in `backend/`, Python 3.12, free plan, Singapore region; the build installs packages
   and pre-downloads the models).
4. It asks for the secret values:
   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Supabase **session pooler** URL from 1.3 |
   | `GROQ_API_KEY` | your Groq key |
   | `SUPABASE_URL` | `https://<project-id>.supabase.co` |
   | `CORS_ORIGINS` | your Vercel URL from step 3; put `http://localhost:3000` for now and change it later |
5. **Apply.** The first build takes 3–5 minutes. When it's **Live**, open
   `https://minutes-api.onrender.com/health` (your exact URL is shown on the service page) →
   `{"status":"ok", ...}`. That address is your **API URL**.

Free Render services sleep after 15 minutes without traffic; the first request after that takes
about a minute while it wakes up. The website shows "Can't reach the server" if you're too quick: retry.

## 3. Website on Vercel

1. <https://vercel.com> → sign in with GitHub → **Add New → Project** → import `minutes-of-meeting`.
2. **Root Directory:** `web` (important). Framework: Next.js (auto-detected).
3. **Environment Variables:**
   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://minutes-api.onrender.com` (your Render URL) |
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://abcdefgh.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the anon / publishable key |
4. **Deploy.** Note the URL, e.g. `https://minutes-hari.vercel.app`.
5. On Render → your service → **Environment**: set `CORS_ORIGINS` to that URL (no trailing slash) →
   Save; Render redeploys by itself.

## 4. Back to Supabase: allowed URLs

*Authentication → URL Configuration*:
- **Site URL:** `https://minutes-hari.vercel.app`
- **Redirect URLs:** add `https://minutes-hari.vercel.app/auth/callback` and
  `http://localhost:3000/auth/callback`

Without this, Google sign-in and email confirmation links bounce to the wrong place.

## 5. Chrome extension

1. `chrome://extensions` → reload the Minutes extension (or Load unpacked → `extension/`).
2. Open the extension → *Settings*: **API URL** = your onrender.com URL, **Website URL** = your Vercel URL → Save.
3. On the website, sign in → **Chrome extension** page → **Connect extension**.
   If the extension asks you to approve the site, open it from the toolbar and click **Approve**.
4. Join a Google Meet call, turn on captions, click **Start taking notes**, then **Stop and save**.

The extension already allows `*.vercel.app` and `*.onrender.com`. For a custom domain, add it to
`content_scripts[1].matches` in `extension/manifest.json`.

## 6. Check everything end to end

1. Open the Vercel URL in a private window → you're sent to **Sign in** → create an account.
2. **New meeting → Paste transcript** → paste a few `Name: text` lines → the meeting page shows
   decisions and action items.
3. **Assistant** → "What are the open tasks?" → it calls `get_action_items`.
4. Sign up as a second user in another browser → it sees **no** meetings from the first.
5. Live: record 1–2 minutes of a Meet call with captions → it opens in Minutes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Website: "Can't reach the server" | Render asleep (wait a minute and retry) or wrong `NEXT_PUBLIC_API_URL` (redeploy Vercel after changing env vars) |
| Browser console: CORS error | `CORS_ORIGINS` on Render doesn't exactly match the Vercel URL (no trailing slash) |
| 401 "Invalid session token" | `SUPABASE_URL` missing/wrong on Render; or an old project using the legacy JWT secret: set `SUPABASE_JWT_SECRET` |
| Render deploy fails connecting to the database | Use the **Session pooler** URL; use a password with only letters and numbers (or URL-encode `@` as `%40`) |
| Render "out of memory" | Check `MODEL_BACKEND=fastembed` is set (PyTorch would need ~1.2 GB) |
| Google sign-in returns to localhost | Fix Site URL / Redirect URLs in step 4 |
| Extension: 0 lines captured | Captions are off in Meet, or Meet changed its page; update `findRegion()` / `readBlocks()` in `extension/content/meet.js` |
