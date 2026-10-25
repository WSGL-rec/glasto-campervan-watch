# Glastonbury campervan watch

Checks the official Glastonbury website every 5 minutes (GitHub sometimes runs it a little later at busy times) for the 2027 campervan / caravan / accommodation sale announcement.

When it finds one, it opens an issue in this repository that mentions @WSGL-rec, so GitHub sends an email and a push notification to the GitHub mobile app.

What it watches:
- **News page** – any new post whose title or text mentions campervans, caravans, accommodation, Worthy View, Sticklinch or tipis.
- **Info page** – the campervan section currently says tickets go on sale "later in the autumn"; it alerts if that wording disappears.

To send a test alert: Actions → Glastonbury campervan watch → Run workflow → tick "Send a test alert".

To stop it after the sale: Actions → Glastonbury campervan watch → ⋯ → Disable workflow.
