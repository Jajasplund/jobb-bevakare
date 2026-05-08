import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ── Konfig ───────────────────────────────────────────────────────────────────
TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK_URL")
CUSTOMERS_FILE = "customers.json"
SEEN_JOBS_FILE = "seen_jobs.json"

# ── Hjälpfunktioner ───────────────────────────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_teams(new_by_customer):
    today = datetime.now().strftime("%Y-%m-%d")

    # Bygg sektioner per kund
    sections = []
    for customer_name, jobs in new_by_customer.items():
        facts = [{"name": j["title"], "value": f"[Öppna annons]({j['url']})"} for j in jobs]
        sections.append({
            "activityTitle": f"**{customer_name}** – {len(jobs)} ny/a annons/er",
            "facts": facts
        })

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": "Nya jobbannonser hos fokuskunder",
        "sections": [
            {
                "activityTitle": f"🔍 Jobbannons-bevakning {today}",
                "activitySubtitle": "Nya annonser sedan senaste bevakning"
            }
        ] + sections
    }

    if not TEAMS_WEBHOOK:
        print("⚠️  Ingen TEAMS_WEBHOOK_URL – skriver bara ut payload")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    resp = requests.post(TEAMS_WEBHOOK, json=payload)
    if resp.status_code != 200:
        print(f"Teams-fel: {resp.status_code} – {resp.text}")

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
    # Första körningen: spara allt men notifiera inte
    first_run = customer_name not in seen_cache

    previously_seen = set(seen_cache.get(customer_name, []))
    current_ids = {j["id"] for j in current_jobs}

    if first_run:
        print(f"  ℹ️  Första körningen – sparar {len(current_jobs)} annonser utan notis")
        return [], current_ids

    new_jobs = [j for j in current_jobs if j["id"] not in previously_seen]
    return new_jobs, current_ids

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

        # Uppdatera cachen med nuvarande annonser
        seen_cache[name] = list(current_ids)

    save_json(SEEN_JOBS_FILE, seen_cache)
    print(f"\n💾 Cache sparad")

    if new_by_customer:
        send_teams(new_by_customer)
        print(f"📨 Teams-notis skickad")
    else:
        print(f"😴 Inga nya annonser den här veckan")

if __name__ == "__main__":
    main()
