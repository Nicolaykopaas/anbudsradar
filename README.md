# Doffin Leads

A lead-generation pipeline for Norwegian public procurement. It finds active public tenders (via [Doffin](https://doffin.no), Norway's national procurement portal), matches each one against relevant small/medium businesses (via [Brønnøysundregistrene](https://www.brreg.no), Norway's official business registry), and scores every match on **relevance** and **realism** — so outreach is targeted, not spam.

Built entirely on free, public government APIs. No paid services, no hosting costs.

## What it does

1. **Fetches tenders** — every active public procurement notice in Norway, with deadline, buyer, estimated value, and industry classification (CPV codes).
2. **Fetches businesses** — small/medium companies from the national business registry, filtered by employee count and industry (NACE codes).
3. **Matches and scores** each tender against candidate businesses:
   - **Match score** — how precisely the industry and location line up.
   - **Realism score** — whether a business this size, this far away, with this much runway before the deadline, could plausibly deliver the contract.
4. **Dashboard** — a local web app to browse matches, review draft outreach emails, and track who's already been contacted.

Nothing is sent automatically. Every email is a draft for manual review.

## Stack

Python, pandas, [Streamlit](https://streamlit.io) — no separate backend, no database, no JS build step. Runs entirely on your machine.

## Running it

```bash
pip install -r requirements.txt

python doffin_fetch.py          # fetch tenders (needs a free Doffin API key)
python brreg_fetch.py           # fetch businesses (no key needed)
python compute_scores.py        # score every match
python generate_email_drafts.py # write draft outreach emails

streamlit run app.py            # open the dashboard
```

See inline docs in each script for setup details (API key registration, employee-count ranges, etc.).

## Design notes

- **Two free registries, one crosswalk.** There's no official mapping between EU procurement codes (CPV) and Norwegian industry codes (NACE) — `cpv_nace.py` is a hand-tuned crosswalk built and refined against real tender data.
- **Distance is computed, not guessed.** Business-to-buyer distance uses a free, offline postal-code coordinate dataset — no geocoding API calls at runtime.
- **Contacted once, never again.** A permanent log excludes any business that's already been reached out to, regardless of outcome — the matching pipeline can't accidentally re-contact anyone.
