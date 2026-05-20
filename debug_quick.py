"""Quick test of specific competitors by name."""
import sys
import json
import os
sys.path.insert(0, os.path.dirname(__file__))

from check_jobs import (
    load_json, _fetch_jobs_from_sitemap, _fetch_intercepted_api_jobs,
    _fetch_adecco_jobs_via_api, _fetch_html_for_site, _fetch_wp_rest_jobs,
    _fetch_click_paginated_jobs, parse_jobs_from_html, clean_city,
    fetch_city_for_job, match_customer_for_competitor_job
)

NAMES = sys.argv[1:] if len(sys.argv) > 1 else ["Poolia", "Professional Nord"]

competitors = load_json("competitors.json")
customers   = load_json("customers.json")

for comp in competitors:
    if comp["name"] not in NAMES:
        continue
    name = comp["name"]
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")

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
        print(f"  FEL: {e}")
        import traceback; traceback.print_exc()
        continue

    matches = []
    for job in jobs:
        cust = match_customer_for_competitor_job(job["url"], job["title"], customers)
        if cust:
            matches.append((cust["name"], job["title"], job.get("city", "")))

    print(f"  Jobb: {len(jobs)}")
    if jobs:
        print("  Exempel (första 5):")
        for j in jobs[:5]:
            print(f"    '{j['title']}' | {j.get('city','')} | {j['url'][:60]}")
    if matches:
        print(f"  Kundmatcher ({len(matches)}):")
        for cust, title, city in matches:
            print(f"    -> {cust}: {title}" + (f" ({city})" if city else ""))
