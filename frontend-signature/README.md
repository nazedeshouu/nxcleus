# Nxcleus signature UI experiment

The third, fully isolated Nxcleus frontend direction. The original `frontend/`
and the earlier `frontend-clean/` experiment remain unchanged.

The signature direction keeps the same routes, API client, state, fixtures,
tests, and copy. It changes the visual system around **The Aperture**:

- mineral paper, carbon ink, and one aged-copper signal;
- cinematic architectural imagery without a logo plaque;
- editorial hierarchy and open ledger surfaces instead of card grids;
- a single boundary-cut motif shared by the landing page and product;
- progressive disclosure for Build Job and Model Activity;
- visible text navigation at every supported width.

Run the backend on port `8000`, then:

```powershell
cd frontend-signature
npm ci
npm run dev
```

The signature UI uses <http://localhost:5175>.
