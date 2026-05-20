"""Quick test: scan all competitors and print job counts + customer matches."""
import json
import sys
import os

# Add parent dir to path so we can import check_jobs
sys.path.insert(0, os.path.dirname(__file__))

from check_jobs import (
    load_json, _fetch_jobs_from_sitemap, _fetch_intercepted_api_jobs,
    _fetch_adecco_jobs_via_api, _fetch_html_for_site, _fetch_wp_rest_jobs,
    _fetch_click_paginated_jobs, parse_jobs_from_html, fetch_city_for_job,
    clean_city, match_customer_for_competitor_job
)

COMPETITORS_FILE = "competitors.json"
CUSTOMERS_FILE   = "customers.json"

competitors = load_json(COMPETITORS_FILE)
customers   = load_json(CUSTOMERS_FILE)

print(f"Testing alla {len(competitors)} konkurrenter...\n")

total_jobs    = 0
total_matches = 0

for comp in competitors:
    name = comp["name"]

    try:
        if comp.get("sitemap_url"):
            jobs = _fetch_jobs_from_sitemap(comp)
        elif comp.get("api_wp_rest_url"):
            jobs = _fetch_wp_rest_jobs(comp)
        elif comp.get("click_page_buttons"):
            jobs = _fetch_click_paginated_jobs(comp)
        elif comp.get("api_intercept_url") and comp.get("api_type") == "adecco_post":
            jobs = _fetch_adecco_jobs_via_api(comp)
        elif comp.get("api_intercept_url"):
            jobs = _fetch_intercepted_api_jobs(comp)
        else:
            scroll_count = comp.get("scroll_count", 10)
            max_pages    = comp.get("max_pages", 1)
            jobs = []
            seen_ids: set = set()
            for page_num in range(1, max_pages + 1):
                html = _fetch_html_for_site(comp, scroll_count=scroll_count, page_num=page_num)
                if not html:
                    break
                page_jobs, _ = parse_jobs_from_html(html, comp, comp["url"])
                new_jobs = [j for j in page_jobs if j["id"] not in seen_ids]
                if not new_jobs and page_num > 1:
                    break
                jobs.extend(new_jobs)
                seen_ids.update(j["id"] for j in new_jobs)
    except Exception as e:
        print(f"  {name}: FEL – {e}")
        continue

    # Match against customers
    matches = []
    for job in jobs:
        cust = match_customer_for_competitor_job(job["url"], job["title"], customers)
        if cust:
            matches.append((cust["name"], job["title"], job.get("city", "")))

    total_jobs    += len(jobs)
    total_matches += len(matches)

    if matches:
        city_part = lambda c: f" ({c})" if c else ""
        match_lines = "\n".join(
            f"    -> {cust}: {title}{city_part(city)}"
            for cust, title, city in matches
        )
        print(f"  {name}: {len(jobs)} jobb, {len(matches)} matcher\n{match_lines}")
    else:
        print(f"  {name}: {len(jobs)} jobb")

print(f"\nTOTALT: {total_jobs} jobb scannades, {total_matches} kundmatchningar\n")
