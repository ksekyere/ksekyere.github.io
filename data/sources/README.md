# Reference data entered by hand

These files feed the Patent viability screen. They change rarely, so they are checked and updated by hand.

## ip_reference.csv

| Column | Meaning | Source | Last checked |
|---|---|---|---|
| `pct_member` | 1 if the country is a Patent Cooperation Treaty (PCT) Contracting State | [WIPO, PCT Contracting States](https://www.wipo.int/export/sites/www/pct/en/docs/list_states.pdf) | November 2026 |
| `paris_member` | 1 if the country is party to the Paris Convention for the Protection of Industrial Property | WIPO-administered treaty lists; Ethiopia's accession entered into force 15 August 2025 ([AIPPI](https://www.aippi.org/news/accession-to-the-paris-convention-confirmed/)) | November 2026 |
| `special301` | Status in the US Trade Representative's annual Special 301 Report: `Priority Foreign Country`, `Priority Watch List`, `Watch List`, blank if not listed, `n/a` for the United States | [USTR, 2026 Special 301 Report](https://ustr.gov/about/policy-offices/press-office/press-releases/2026/april/ustr-releases-2026-special-301-report-intellectual-property-protection-and-enforcement) | April 2026 report |
| `note` | Anything a reader should know about the row | | |

**When to update:** each April, when USTR publishes the new Special 301 Report, update `special301` and change
`SPECIAL301_YEAR` at the top of `pipeline/build_country_conditions.py`. Check WIPO's PCT list at the same time.

## World Justice Project file (optional)

If a World Justice Project Rule of Law Index data file (`.xlsx`) is placed in this folder, the pipeline adds each
country's **Civil Justice** score (Factor 7: whether courts are accessible, timely and effectively enforced), and the
screen uses it as an extra enforcement check. Download the historical data file from
https://worldjusticeproject.org/rule-of-law-index/downloads and save it here with "wjp" in its file name.
Without it, the screen relies on the World Bank's rule of law estimate and the Special 301 status.
