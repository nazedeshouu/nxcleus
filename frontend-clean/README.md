# Nxcleus clean UI experiment

An independent frontend copy for testing a calmer, lower-complexity visual direction without changing `frontend/`.

The experiment keeps the same routes, API client, state model, fixtures, and tests. Its design changes focus on:

- a quieter institutional palette with one muted accent;
- progressive disclosure in Build Job;
- an explained, auto-selected Model Activity flow with plain-language summaries and optional audit detail;
- a calmer landing hero and boundary presentation.

Run the backend on port `8000`, then:

```powershell
cd frontend-clean
npm ci
npm run dev
```

The clean UI uses <http://localhost:5174>. The original frontend remains on <http://localhost:5173>.
