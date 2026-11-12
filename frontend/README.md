# PactGuard AI frontend

React 19, Vite, Tailwind 4 and AG Studio. Two views behind a hash route:

- **Mission Control** (`#/`): the mandate form and what to buy, the run (discovery rows, activity timeline, negotiation, firewall decisions, settlement, post-purchase checks), the evidence ledger, webhook inspector and dispute desk. Code in `src/features/`.
- **Command Center** (`#/studio`): a seven-page AG Studio report over the ledger and the merchant's PayPal account, with a Live feed. Code in `src/studio/`; the bundle loads only when the route opens.

```bash
npm install
npm run dev      # :5173, proxies /api to http://localhost:8000 (set API_TARGET to change it)
npm run build    # tsc -b && vite build
npx oxlint       # lint
```

The AG Studio licence key goes in `frontend/.env.local` as `VITE_AG_STUDIO_LICENSE` (see `.env.example`). It ships in the browser bundle by design; never put a PayPal or LLM key in a `VITE_` variable. The server-side setup is in [`../docs/OPERATIONS.md`](../docs/OPERATIONS.md).
