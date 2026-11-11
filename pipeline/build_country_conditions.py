"""
build_country_conditions.py

Builds the data file behind the Country Conditions Dashboard on ksekyere.github.io.

Pulls annual indicators from the World Bank API (World Development Indicators and
Worldwide Governance Indicators) for 27 countries, 2000 to the latest year, and writes:

    data/country_conditions.json      read by the dashboard
    data/country_conditions_long.csv  the same data in tidy (long) form, for analysis

Run from the repository root:

    pip install -r pipeline/requirements.txt
    python pipeline/build_country_conditions.py

No API key is needed. The script is safe to rerun: it rebuilds both files from scratch.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# --------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]          # repository root
OUT_JSON = ROOT / "data" / "country_conditions.json"
OUT_CSV = ROOT / "data" / "country_conditions_long.csv"

START_YEAR = 2000
END_YEAR = date.today().year
API = "https://api.worldbank.org/v2"

# Country selection rule (stated on the site):
#   1. cover each focus region, plus the US and two high-income peers for comparison;
#   2. within each region, take the largest economies by GDP;
#   3. drop countries with large data gaps (e.g. Venezuela, Sudan, Russia after 2022, Iran).
REGIONS = [
    {"id": "east_africa",     "name": "East Africa",     "countries": ["KEN", "ETH", "TZA", "UGA"]},
    {"id": "west_africa",     "name": "West Africa",     "countries": ["NGA", "GHA", "CIV", "SEN"]},
    {"id": "eastern_europe",  "name": "Eastern Europe",  "countries": ["POL", "ROU", "UKR", "HUN"]},
    {"id": "latin_america",   "name": "Latin America",   "countries": ["BRA", "MEX", "ARG", "COL"]},
    {"id": "central_america", "name": "Central America", "countries": ["GTM", "CRI", "HND", "SLV"]},
    {"id": "west_asia",       "name": "West Asia",       "countries": ["TUR", "SAU", "ARE", "JOR"]},
    {"id": "comparison",      "name": "Comparison",      "countries": ["USA", "GBR", "DEU"]},
]

# Indicators, grouped into themes.
#   codes:     World Bank indicator codes, tried in order (the first one with data is used;
#              later codes are fallbacks for indicators the World Bank has renamed)
#   source:    World Bank API source id (2 = World Development Indicators,
#              3 = Worldwide Governance Indicators)
#   search:    optional; if none of the codes work, look the indicator up by this name
#              (the World Bank renamed the governance codes in its 2025 update)
#   scale:     optional; values are divided by this (e.g. 1e9 to show US$ billions)
#   direction: "up" if higher is generally better, "down" if lower is better,
#              None if neither (used only for wording on the dashboard, never for scoring)
THEMES = [
    {"id": "governance", "name": "Governance and rule of law", "indicators": [
        {"id": "rule_of_law",  "codes": ["GOV_WGI_RL.EST", "GOV_WGI_RL_EST", "RL.EST"], "source": 3, "search": "Rule of Law", "short": "Rule of law",
         "unit": "score", "decimals": 2, "direction": "up",
         "note": "Estimate from about -2.5 (weak) to 2.5 (strong)."},
        {"id": "regulatory",   "codes": ["GOV_WGI_RQ.EST", "GOV_WGI_RQ_EST", "RQ.EST"], "source": 3, "search": "Regulatory Quality", "short": "Regulatory quality",
         "unit": "score", "decimals": 2, "direction": "up",
         "note": "Estimate from about -2.5 (weak) to 2.5 (strong)."},
        {"id": "corruption",   "codes": ["GOV_WGI_CC.EST", "GOV_WGI_CC_EST", "CC.EST"], "source": 3, "search": "Control of Corruption", "short": "Control of corruption",
         "unit": "score", "decimals": 2, "direction": "up",
         "note": "Estimate from about -2.5 (weak) to 2.5 (strong)."},
        {"id": "stability",    "codes": ["GOV_WGI_PV.EST", "GOV_WGI_PV_EST", "PV.EST"], "source": 3, "search": "Political Stability", "short": "Political stability",
         "unit": "score", "decimals": 2, "direction": "up",
         "note": "Political stability and absence of violence; about -2.5 to 2.5."},
    ]},
    {"id": "trade", "name": "Trade and investment", "indicators": [
        {"id": "fdi",          "codes": ["BX.KLT.DINV.WD.GD.ZS"], "source": 2, "short": "Foreign direct investment",
         "unit": "% of GDP", "decimals": 1, "direction": None,
         "note": "Net inflows of foreign direct investment."},
        {"id": "trade_open",   "codes": ["NE.TRD.GNFS.ZS"], "source": 2, "short": "Trade openness",
         "unit": "% of GDP", "decimals": 0, "direction": None,
         "note": "Exports plus imports of goods and services."},
        {"id": "current_acct", "codes": ["BN.CAB.XOKA.GD.ZS"], "source": 2, "short": "Current account balance",
         "unit": "% of GDP", "decimals": 1, "direction": None,
         "note": "Positive values are surpluses, negative values deficits."},
    ]},
    {"id": "innovation", "name": "Innovation and intellectual property", "indicators": [
        {"id": "pat_res",      "codes": ["IP.PAT.RESD"], "source": 2, "short": "Patent applications by residents",
         "unit": "applications", "decimals": 0, "direction": None,
         "note": "Patent applications filed by residents of the country, all patent offices reporting to WIPO."},
        {"id": "pat_nres",     "codes": ["IP.PAT.NRES"], "source": 2, "short": "Patent applications by foreigners",
         "unit": "applications", "decimals": 0, "direction": None,
         "note": "Patent applications filed in the country by nonresidents; a signal of foreign interest in protecting inventions there."},
        {"id": "trademarks",   "codes": ["IP.TMK.NRCT"], "source": 2, "short": "Trademark applications by foreigners",
         "unit": "applications", "decimals": 0, "direction": None,
         "note": "Trademark applications filed in the country by nonresidents, by count; a signal of foreign brands entering the market."},
        {"id": "rnd",          "codes": ["GB.XPD.RSDV.GD.ZS"], "source": 2, "short": "R&D spending",
         "unit": "% of GDP", "decimals": 2, "direction": None,
         "note": "Gross domestic spending on research and development."},
        {"id": "hightech",     "codes": ["TX.VAL.TECH.MF.ZS"], "source": 2, "short": "High-tech exports",
         "unit": "% of manufactured exports", "decimals": 0, "direction": None,
         "note": "Exports with high R&D intensity, such as aerospace, computers, pharmaceuticals and scientific instruments."},
        {"id": "ip_paid",      "codes": ["BM.GSR.ROYL.CD"], "source": 2, "short": "IP payments abroad",
         "unit": "US$ billions", "decimals": 2, "direction": None, "scale": 1e9,
         "note": "Payments to other countries for the use of patents, trademarks, copyrights and similar rights, current US dollars."},
        {"id": "ip_recv",      "codes": ["BX.GSR.ROYL.CD"], "source": 2, "short": "IP receipts from abroad",
         "unit": "US$ billions", "decimals": 2, "direction": None, "scale": 1e9,
         "note": "Receipts from other countries for the use of the country's intellectual property, current US dollars."},
        {"id": "gdp",          "codes": ["NY.GDP.MKTP.CD"], "source": 2, "short": "GDP (economy size)",
         "unit": "US$ billions", "decimals": 0, "direction": None, "scale": 1e9,
         "note": "Gross domestic product in current US dollars; a rough guide to market size."},
    ]},
    {"id": "people", "name": "People and inequality", "indicators": [
        {"id": "unemployment", "codes": ["SL.UEM.TOTL.ZS"], "source": 2, "short": "Unemployment",
         "unit": "% of labor force", "decimals": 1, "direction": "down",
         "note": "Modeled ILO estimate."},
        {"id": "gini",         "codes": ["SI.POV.GINI"], "source": 2, "short": "Income inequality (Gini)",
         "unit": "index", "decimals": 1, "direction": "down",
         "note": "0 is perfect equality, 100 perfect inequality. Measured in survey years only."},
        {"id": "remittances",  "codes": ["BX.TRF.PWKR.DT.GD.ZS"], "source": 2, "short": "Remittances received",
         "unit": "% of GDP", "decimals": 1, "direction": None,
         "note": "Personal transfers and compensation of employees received."},
    ]},
    {"id": "health", "name": "Health", "indicators": [
        {"id": "life_exp",     "codes": ["SP.DYN.LE00.IN"], "source": 2, "short": "Life expectancy",
         "unit": "years", "decimals": 1, "direction": "up",
         "note": "Life expectancy at birth, total."},
        {"id": "under5",       "codes": ["SH.DYN.MORT"], "source": 2, "short": "Under-5 mortality",
         "unit": "per 1,000 births", "decimals": 0, "direction": "down",
         "note": "Deaths before age 5 per 1,000 live births."},
        {"id": "health_spend", "codes": ["SH.XPD.CHEX.GD.ZS"], "source": 2, "short": "Health spending",
         "unit": "% of GDP", "decimals": 1, "direction": None,
         "note": "Current health expenditure."},
    ]},
    {"id": "environment", "name": "Environment and climate", "indicators": [
        {"id": "co2",          "codes": ["EN.GHG.CO2.PC.CE.AR5", "EN.ATM.CO2E.PC"], "source": 2,
         "short": "CO₂ emissions per person", "unit": "tonnes", "decimals": 1, "direction": "down",
         "note": "Carbon dioxide emissions per person, excluding land use change."},
        {"id": "renewables",   "codes": ["EG.FEC.RNEW.ZS"], "source": 2, "short": "Renewable energy",
         "unit": "% of energy use", "decimals": 0, "direction": "up",
         "note": "Renewable share of total final energy consumption. Includes traditional biomass."},
        {"id": "pm25",         "codes": ["EN.ATM.PM25.MC.M3"], "source": 2, "short": "Air pollution (PM2.5)",
         "unit": "µg/m³", "decimals": 0, "direction": "down",
         "note": "Mean annual exposure to fine particulate matter."},
    ]},
]

# --------------------------------------------------------------------------------------
# World Bank API helpers
# --------------------------------------------------------------------------------------

session = requests.Session()
session.headers["User-Agent"] = "country-conditions-dashboard (github.com/ksekyere)"


def get_json(url: str, params: dict, tries: int = 4) -> list:
    """GET a World Bank API URL and return the parsed JSON, retrying on network errors."""
    for attempt in range(1, tries + 1):
        try:
            r = session.get(url, params=params, timeout=60)
            r.raise_for_status()
            payload = r.json()
            # The API returns [metadata, records]; errors come back as [{"message": ...}]
            if isinstance(payload, list) and payload and "message" in payload[0]:
                return []
            return payload
        except (requests.RequestException, ValueError) as err:
            if attempt == tries:
                print(f"  ! giving up on {url}: {err}", file=sys.stderr)
                return []
            time.sleep(2 * attempt)
    return []


def fetch_indicator(code: str, source: int | None, countries: list[str]) -> pd.DataFrame:
    """All countries' annual values for one indicator, as a tidy DataFrame."""
    url = f"{API}/country/{';'.join(countries)}/indicator/{code}"
    params = {"format": "json", "date": f"{START_YEAR}:{END_YEAR}", "per_page": 20000}
    if source is not None:
        params["source"] = source
    payload = get_json(url, params)
    if len(payload) < 2 or not payload[1]:
        return pd.DataFrame(columns=["iso3", "year", "value"])
    df = pd.DataFrame(
        {"iso3": rec["countryiso3code"], "year": int(rec["date"]), "value": rec["value"]}
        for rec in payload[1]
    )
    return df.dropna(subset=["value"])


def search_indicator(source: int, name: str) -> list[str]:
    """Find indicator codes in a source whose name contains `name` and is an estimate."""
    payload = get_json(f"{API}/sources/{source}/indicators", {"format": "json", "per_page": 5000})
    try:
        hits = [i["id"] for i in payload[1]
                if name.lower() in i.get("name", "").lower() and "estimate" in i.get("name", "").lower()]
    except (IndexError, TypeError, KeyError):
        return []
    return hits


def fetch_indicator_name(code: str, source: int | None) -> tuple[str, str]:
    """Official indicator name and source organization, for citations."""
    params = {"format": "json"}
    if source is not None:
        params["source"] = source
    payload = get_json(f"{API}/indicator/{code}", params)
    try:
        meta = payload[1][0]
        return meta.get("name", code), (meta.get("sourceOrganization") or "").strip()
    except (IndexError, TypeError, KeyError):
        return code, ""


def fetch_country_names(countries: list[str]) -> dict[str, str]:
    payload = get_json(f"{API}/country/{';'.join(countries)}", {"format": "json", "per_page": 100})
    try:
        return {c["id"]: c["name"] for c in payload[1]}
    except (IndexError, TypeError, KeyError):
        return {}


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------

def main() -> None:
    countries = [c for region in REGIONS for c in region["countries"]]
    names = fetch_country_names(countries)
    missing_names = [c for c in countries if c not in names]
    if missing_names:
        print(f"  ! no name returned for: {', '.join(missing_names)}", file=sys.stderr)

    frames, indicators = [], {}
    for theme in THEMES:
        for ind in theme["indicators"]:
            df, used = pd.DataFrame(), None
            # Try each listed code with its source, then without a source filter
            attempts = [(code, src) for src in (ind["source"], None) for code in ind["codes"]]
            for code, src in attempts:
                df = fetch_indicator(code, src, countries)
                if not df.empty:
                    used = code
                    break
            # Last resort: look the code up by name in the source's indicator list
            if used is None and ind.get("search"):
                for code in search_indicator(ind["source"], ind["search"]):
                    df = fetch_indicator(code, ind["source"], countries)
                    if not df.empty:
                        used = code
                        print(f"  (found {ind['short']} by name as {code})")
                        break
            if used is None:
                print(f"  ! no data for {ind['short']} ({', '.join(ind['codes'])}); skipped", file=sys.stderr)
                continue

            if ind.get("scale"):
                df["value"] = df["value"] / ind["scale"]
            official_name, organization = fetch_indicator_name(used, ind["source"])
            if official_name == used:   # name lookup can fail for renamed codes; try without source
                official_name, organization = fetch_indicator_name(used, None)
            df["indicator"] = ind["id"]
            frames.append(df)
            indicators[ind["id"]] = {
                "short": ind["short"],
                "name": official_name,
                "code": used,
                "unit": ind["unit"],
                "decimals": ind["decimals"],
                "direction": ind["direction"],
                "note": ind["note"],
                "source": "Worldwide Governance Indicators" if ind["source"] == 3 else "World Development Indicators",
                "organization": organization,
            }
            print(f"  {ind['short']:<28} {used:<24} {len(df):>5} values, "
                  f"{df['year'].min()}–{df['year'].max()}")

    if not frames:
        sys.exit("No data downloaded. Check your internet connection and try again.")

    long = pd.concat(frames, ignore_index=True)
    long = long[long["iso3"].isin(countries)]
    long["value"] = long["value"].astype(float)
    long = long.sort_values(["indicator", "iso3", "year"]).reset_index(drop=True)

    # Tidy CSV for analysis in pandas, R or a spreadsheet
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    long.assign(country=long["iso3"].map(names))[
        ["indicator", "iso3", "country", "year", "value"]
    ].to_csv(OUT_CSV, index=False)

    # Compact JSON for the dashboard: data[indicator][iso3] = [[year, value], ...]
    data: dict[str, dict[str, list]] = {}
    for (ind_id, iso3), grp in long.groupby(["indicator", "iso3"]):
        dec = indicators[ind_id]["decimals"] + 2   # keep a little extra precision for charts
        data.setdefault(ind_id, {})[iso3] = [[int(y), round(float(v), dec)] for y, v in zip(grp["year"], grp["value"])]

    region_of = {c: r["id"] for r in REGIONS for c in r["countries"]}
    out = {
        "meta": {
            "title": "Country Conditions",
            "source": "World Bank, World Development Indicators and Worldwide Governance Indicators",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "first_year": int(long["year"].min()),
            "last_year": int(long["year"].max()),
            "sample": False,
        },
        "regions": [{"id": r["id"], "name": r["name"], "countries": r["countries"]} for r in REGIONS],
        "countries": {c: {"name": names.get(c, c), "region": region_of[c]} for c in countries},
        "themes": [
            {"id": t["id"], "name": t["name"],
             "indicators": [i["id"] for i in t["indicators"] if i["id"] in indicators]}
            for t in THEMES
        ],
        "indicators": indicators,
        "data": data,
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    size_kb = OUT_JSON.stat().st_size / 1024
    print(f"\nWrote {OUT_JSON.relative_to(ROOT)} ({size_kb:.0f} KB) and {OUT_CSV.relative_to(ROOT)}")
    print(f"{len(indicators)} indicators, {len(countries)} countries, "
          f"{out['meta']['first_year']}–{out['meta']['last_year']}")


if __name__ == "__main__":
    main()
