# ksekyere.github.io

Personal site of Kofi Forkuo-Sekyere: economic and policy research.

Live at https://ksekyere.github.io

## Country Conditions Dashboard

The dashboard reads `data/country_conditions.json`, built by a Python pipeline from World Bank data
(World Development Indicators and Worldwide Governance Indicators) for 27 countries, 2000 to the latest year.

**Rebuild the data by hand**

```bash
python3 -m pip install -r pipeline/requirements.txt
python3 pipeline/build_country_conditions.py
```

This writes `data/country_conditions.json` (for the dashboard) and `data/country_conditions_long.csv`
(the same data in long format, for analysis). No API key is needed.

**Automatic updates.** `.github/workflows/update-data.yml` reruns the pipeline on the 5th of each month
and commits the new data if anything changed. Run it any time from the Actions tab → Update country data → Run workflow.

**Countries** were chosen by a stated rule: the largest economies by GDP in each focus region
(East Africa, West Africa, Eastern Europe, Latin America, Central America, West Asia), excluding countries with
large data gaps, plus the United States, United Kingdom and Germany for comparison. The list is set at the top
of `pipeline/build_country_conditions.py`.

Data is for research and discussion; it is not investment, legal or tax advice.
