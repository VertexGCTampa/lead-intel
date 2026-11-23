# Vertex lead scanner

Every Monday morning this scans Hillsborough and Pinellas bid portals and planning agendas,
uses Claude to pull out each project, scores it against Vertex's fit profile, updates a
dashboard, and emails the top new leads.

## How it works

1. `config/sources.yaml` lists each source. A browser opens each page (or the newest agenda PDFs).
2. Claude reads the text and returns one record per project: type, stage, value, size, owner, design team.
3. `config/fit_profile.yaml` drops what doesn't fit (civil, single-trade, over the bonded limit,
   renovations, condos and so on) and scores the rest into Pursue, Watch or Low.
4. Leads at the same residential address are merged, so a teardown that later shows up with a
   variance or permit becomes one lead with a history.
5. Results are saved in `data/leads.json`, the dashboard is rebuilt in `docs/index.html`,
   and the digest email goes out.

## Setup

1. **Create a GitHub repository** and upload everything in this folder.
2. **Add secrets** under Settings > Secrets and variables > Actions:
   - `ANTHROPIC_API_KEY`: from console.anthropic.com
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: the mailbox that sends the digest
   - `DIGEST_TO`: where the digest goes; `SMTP_FROM` is optional
   - Under the Variables tab, add `DASHBOARD_URL` once Pages is on (step 3)

   Microsoft 365 tenants often have SMTP sign-in turned off. If the email step fails, ask your IT
   provider to enable SMTP AUTH for the sending mailbox, or use a separate sending account.
3. **Turn on the dashboard:** Settings > Pages > Deploy from a branch > `main`, folder `/docs`.
   On GitHub's free plan the repository must be public for Pages to work; paid plans allow a private
   repository. The leads themselves are public records. Statuses you set (Pursuing, Passed and so on)
   are saved in your browser only, not in the repository.
4. **Test one source:** Actions > Weekly lead scan > Run workflow, and enter `stpete_bids` in the
   source box. Check the run log and the dashboard. Then run it again with the box empty for a full scan.

After that it runs on its own every Monday.

## Turning on more sources

Sources marked `status: verify` are confirmed agencies whose exact page I couldn't confirm.
Find the page, paste the URL into `url`, set `enabled: true`, and test with a single-source run.

## Tuning

Everything that decides what you see is in `config/fit_profile.yaml`: value limits, the custom-home
size minimum, the townhome unit cap, priority ZIP codes, points per project type and the tier cutoffs.
Add owners, architects and brokers you work with under `relationships.names` to boost their projects.

## Tests

`python -m pytest tests` checks the scoring rules, address merging and dashboard build without
touching the internet.

## Next phases

- Residential: demolition and new-home permits (Tampa, Hillsborough, Pinellas) and lot sales from the
  property appraisers
- Email-based sources: DemandStar alerts (Largo, Dunedin, Tampa construction) and the Tampa CARES email
- Lease announcements and business news
