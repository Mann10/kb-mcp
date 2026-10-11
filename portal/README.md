# KB Portal (Phase 10 auth shell)

Vite + React frontend for the UIF Token Portal. Phase 10 ships auth pages only:
signup/login, session header, admin-gated placeholder with denial state.

## Local dev

```bash
npm install
cp .env.example .env
# fill the three VITE_ vars in .env
npm run dev
```

Required `.env` values (all public by construction):

- `VITE_SUPABASE_URL` — same value as the backend `SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY` — same value as the backend `SUPABASE_ANON_KEY`
- `VITE_API_URL` — Horizon server base URL (e.g. `https://kb-mcp.fastmcp.app`)

Build check (uses dummy example values, no live backend needed):

```bash
npm run build
```

## Vercel deploy

1. Import the repo in Vercel, set **root directory** to `portal`.
2. Set the three `VITE_` env vars above (`VITE_SUPABASE_URL`,
   `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`) in the Vercel project env.
3. Deploy. SPA rewrites (`vercel.json`) keep `/admin` working on refresh.

> **SC-3 note:** Vercel envs must NEVER include `service_role` keys.
> The browser holds only the Supabase user JWT; privileged checks go
> through the BFF (`SUPABASE_SERVICE_ROLE_KEY` lives on Horizon only).

## Backend env checklist (Horizon server)

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` (Horizon server env ONLY, never Vercel)
- `ADMIN_EMAILS` — comma-separated owner email(s)
- `PORTAL_ORIGINS` — Vercel app URL + `http://localhost:5173`
