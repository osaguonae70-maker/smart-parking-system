# Debug Session: ui-not-updating [OPEN]

## User Report
- User says they are not seeing any changes after the architecture update.

## Expected
- Admin dashboard should show separate simulation and real-user metrics.
- Portal should show real-user slots as `R1-R30`.
- Simulation zone should remain separate as `S1-S20`.

## Hypotheses
1. The running Flask process is serving older code because it was not restarted.
2. The browser is showing cached HTML or JavaScript.
3. The user is viewing a route/page that was not changed by the architecture update.
4. The backend is updated, but `/api/admin-stats` or `/api/slots` is not returning the new payload.
5. A runtime rendering issue is hiding the new data on the page.

## Evidence Plan
- Verify what the running server serves for the portal and admin pages.
- Verify current API payload shape for slots and admin stats.
- Compare served HTML with the updated template contents.
- Only instrument if the server responses do not already reveal the mismatch.

## Status
- Session initialized.
- Awaiting runtime evidence.
