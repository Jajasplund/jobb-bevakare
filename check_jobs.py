import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ── Konfig ───────────────────────────────────────────────────────────────────
CUSTOMERS_FILE = "customers.json"
SEEN_JOBS_FILE = "seen_jobs.json"

# ── Hjälpfunktioner ───────────────────────────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Scraping ──────────────────────────────────────────────────────────────────
def fetch_jobs(customer):
    name = customer["name"]
    url = customer["url"]
    pattern = customer["job_link_pattern"]

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Kunde inte hämta {name}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            base = url.split("/")[0] + "//" + url.split("/")[2]
            href = base + href
        if pattern in href and href not in seen_urls:
            title = a.get_text(strip=True)
            if title and len(title) > 3:
                seen_urls.add(href)
                jobs.append({"id": href, "title": title, "url": href})

    print(f"  → {name}: hittade {len(jobs)} annonser live")
    return jobs

# ── Jämför med cache ──────────────────────────────────────────────────────────
def find_new_jobs(customer_name, current_jobs, seen_cache):
    first_run = customer_name not in seen_cache

    previously_seen = set(seen_cache.get(customer_name, []))
    current_ids = {j["id"] for j in current_jobs}

    if first_run:
        print(f"  ℹ️  Första körningen – sparar {len(current_jobs)} annonser utan notis")
        return [], current_ids

    new_jobs = [j for j in current_jobs if j["id"] not in previously_seen]
    return new_jobs, current_ids

# ── Bygg mejlinnehåll ─────────────────────────────────────────────────────────
def build_email_body(new_by_customer):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"Jobbannons-bevakning – {today}\n"]
    lines.append("Följande nya annonser hittades hos dina fokuskunder:\n")

    for customer_name, jobs in new_by_customer.items():
        lines.append(f"\n{customer_name} – {len(jobs)} ny/a annons/er:")
        for j in jobs:
            lines.append(f"  - {j['title']}")
            lines.append(f"    {j['url']}")

    lines.append("\n---")
    lines.append("Jobbannons-bevakaren (GitHub Actions)")
    return "\n".join(lines)

# ── Skriv till fil för GitHub Actions ────────────────────────────────────────
def write_output(new_by_customer):
    body = build_email_body(new_by_customer)
    today = datetime.now().strftime("%Y-%m-%d")

    # Spara ämnesrad och body som separata filer
    with open("email_subject.txt", "w", encoding="utf-8") as f:
        total = sum(len(j) for j in new_by_customer.values())
        f.write(f"🔍 Jobbbevakning {today} – {total} ny/a annons/er")

    with open("email_body.txt", "w", encoding="utf-8") as f:
        f.write(body)

    print("\n📧 Mejlinnehåll sparat")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    customers = load_json(CUSTOMERS_FILE)
    seen_cache = load_json(SEEN_JOBS_FILE)

    new_by_customer = {}

    for customer in customers:
        name = customer["name"]
        print(f"\nKollar {name}...")

        current_jobs = fetch_jobs(customer)
        if not current_jobs:
            continue

        new_jobs, current_ids = find_new_jobs(name, current_jobs, seen_cache)

        if new_jobs:
            print(f"  🆕 {len(new_jobs)} nya jobb!")
            for j in new_jobs:
                print(f"     – {j['title']}")
            new_by_customer[name] = new_jobs
        else:
            print(f"  ✅ Inga nya jobb")

        seen_cache[name] = list(current_ids)

    save_json(SEEN_JOBS_FILE, seen_cache)
    print(f"\n💾 Cache sparad")

    if new_by_customer:
        write_output(new_by_customer)
    else:
        print(f"😴 Inga nya annonser den här veckan")
        # Skapa tomma filer så workflow inte kraschar
        open("email_subject.txt", "w").close()
        open("email_body.txt", "w").close()

if __name__ == "__main__":
    main()
