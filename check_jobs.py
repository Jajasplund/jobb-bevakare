import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime

CUSTOMERS_FILE = "customers.json"
SEEN_JOBS_FILE = "seen_jobs.json"

BLUE_COLLAR_KEYWORDS = [
    "lagermedarbetare", "lagerarbetare",
    "kassör", "kassörska",
    "chaufför", "lastbilsförare", "busförare", "bussförare",
    "truckförare", "truckoperatör",
    "städare", "städerska",
    "maskinoperatör", "produktionsoperatör",
    "montör",
    "packare", "packmedarbetare",
    "butikssäljare", "butiksmedarbetare",
    "svetsare", "elektriker", "rörmokare", "snickare", "plåtslagare",
    "kock", "köksbiträde",
    "säkerhetsvakt", "väktare",
    "sommarvikarie", "säsongsarbetare",
]

SWEDISH_CITIES = {
    "stockholm", "göteborg", "malmö", "uppsala", "linköping", "västerås",
    "örebro", "norrköping", "helsingborg", "jönköping", "umeå", "lund",
    "borås", "sundsvall", "gävle", "södertälje", "karlstad", "växjö",
    "halmstad", "solna", "mölndal", "huddinge", "nacka", "järfälla",
    "haninge", "skellefteå", "falun", "eskilstuna", "östersund",
    "trollhättan", "karlskrona", "kalmar", "kristianstad", "skövde",
    "lidköping", "visby", "varberg", "uddevalla", "borlänge", "nyköping",
    "täby", "upplands väsby", "sigtuna", "lidingö", "norrtälje", "tyresö",
    "botkyrka", "nynäshamn", "värmdö", "ekerö", "jordbro", "kallhäll",
    "häggvik", "enköping", "mora", "åseda", "helsingborg", "hovsjö",
    "arendal", "kiruna", "mjällby", "sölvesborg",
    "remote", "distans", "hybridarbete", "hybrid", "hela sverige", "sverige", "sweden",
}

NON_SWEDISH_CITIES = {
    "oslo", "bergen", "trondheim", "stavanger",
    "köpenhamn", "copenhagen", "aarhus", "odense", "denmark",
    "helsinki", "helsingfors", "tampere", "finland",
    "norway", "norge",
    "london", "berlin", "hamburg", "amsterdam", "paris",
    "warsaw", "warszawa", "riga", "tallinn", "vilnius", "vilniuje", "panevežys", "panevėžyje",
    "new york", "san francisco", "toronto",
    "barcelona",
    "estonia", "latvia", "lithuania",
    "u.s.", "u.s.a.", " usa", "united states",
    "virtual", "in-house team",
}

US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "pr", "dc",
}

LOCATION_CLASSES = re.compile(
    r"location|city|ort|stad|place|region|område", re.IGNORECASE
)

GENERIC_LINK_TEXTS = {
    "läs mer", "read more", "se mer", "apply", "ansök", "ansök nu",
    "prenumerera", "prenumerera på lediga jobb", "prenumerera på din framtida tjänst",
    "prenumerera på våra jobb", "prenumerera på jobb",
    "alla platser", "alla våra platser", "lediga jobb", "lediga tjänster",
    "alla lediga tjänster", "alla jobb", "all jobs", "se alla jobb",
    "cookie policy", "start", "log in as employee", "log in to connect", "connect",
    "my job list", "our job openings", "career site", "job areas",
    "employee login", "candidate connect login",
    "jag är skanska", "en värld av möjligheter", "data & privacy", "start your career",
    "hitta ditt nya jobb", "våra lediga tjänster", "jobba hos oss",
    "arbeta på seb", "vår rekryteringsprocess", "vanliga frågor och svar",
    "vår kultur", "arbetsområden", "lärande och utveckling", "ledarskap",
    "möt våra medarbetare", "nyexaminerade och studenter", "kontakta oss", "svenska",
    "medarbetares fördelar och förmåner",
    "it and data", "finance and analysis", "customer service and advice", "all job areas",
    "people, marketing, communication and support", "risk management, compliance and legal",
    "menyjobba hos oss", "karriär", "om oss",
    "frågor och svar", "hitta ditt nya jobb",
    "about swedbank", "vilken är din framtida arbetsplats?",
    "svenska - sv", "swedish - sv",
    "select which cookies you accept",
    "vår affär", "hitta oss",
    "öppnas i nytt fönster", "opens in new window",
    "syfte och värderingar", "bolagsstyrning", "ekonomi",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_blue_collar(title):
    t = title.lower()
    return any(kw in t for kw in BLUE_COLLAR_KEYWORDS)


def get_patterns(customer):
    patterns = customer.get("job_link_patterns")
    if patterns:
        return patterns if isinstance(patterns, list) else [patterns]
    p = customer.get("job_link_pattern", "")
    return [p] if p else []


def href_matches(href, patterns):
    return any(p in href for p in patterns)


def extract_city_from_title(title):
    # ICA pattern: "PlatsSolna" or "PlatsStockholm"
    m = re.search(r'Plats([A-ZÅÄÖ][a-zåäö]+)', title)
    if m:
        return m.group(1)
    # Swedish patterns: "till Stockholm", "i Göteborg", "– Malmö"
    patterns = [
        r"\btill\s+([A-ZÅÄÖ][a-zåäö]+(?:\s[A-ZÅÄÖ][a-zåäö]+)?)\s*$",
        r"\bi\s+([A-ZÅÄÖ][a-zåäö]+(?:\s[A-ZÅÄÖ][a-zåäö]+)?)\s*$",
        r"[–\-]\s*([A-ZÅÄÖ][a-zåäö]+(?:\s[A-ZÅÄÖ][a-zåäö]+)?)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, title)
        if m:
            return m.group(1)
    return None


def title_has_non_swedish_location(title):
    t = title.lower()
    return any(city in t for city in NON_SWEDISH_CITIES)


def get_link_title(anchor):
    """Prefer headings inside the link (Teamtailor etc.) over raw get_text()."""
    for tag in anchor.find_all(["h2", "h3", "h4", "strong"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 5:
            return text
    for tag in anchor.find_all(True):
        classes = " ".join(tag.get("class", []))
        if re.search(r'title|heading|job.?name|position.?name', classes, re.IGNORECASE):
            text = tag.get_text(strip=True)
            if text and 5 < len(text) < 200:
                return text
    return anchor.get_text(strip=True)


def get_ancestor_title(anchor):
    """For generic 'Läs mer' links, find job title in nearest ancestor container."""
    el = anchor.parent
    for _ in range(4):
        if not el:
            break
        for tag in el.find_all(["h2", "h3", "h4"]):
            text = tag.get_text(strip=True)
            if text and 5 < len(text) < 150 and text.lower() not in GENERIC_LINK_TEXTS:
                return text
        # Also look at sibling td/p cells (Toyota table layout)
        for tag in el.find_all(["td", "p"]):
            if tag == anchor.parent:
                continue
            text = tag.get_text(strip=True)
            if text and 5 < len(text) < 150 and text.lower() not in GENERIC_LINK_TEXTS:
                return text
        el = el.parent if el else None
    return None


def clean_title(title):
    """Strip common metadata appended after the job title."""
    title = re.sub(r'^Läs mer om\s+', '', title).strip()
    if "·" in title:
        title = title.split("·")[0].strip()
    # Remove ICA "(PlatsSolna)" city suffix
    title = re.sub(r'\s*\(Plats[A-ZÅÄÖ][a-zåäö]+(?:\s[A-ZÅÄÖ][a-zåäö]+)?\)', '', title).strip()
    # Remove Teamtailor carousel overflow: trailing "(...)" containing another job snippet
    title = re.sub(r'\s*\([^)]{20,}\)', '', title).strip()
    # Remove unclosed parenthesis left after "·" split
    if '(' in title and title.count('(') > title.count(')'):
        title = title[:title.rfind('(')].strip()
    # Remove accessibility link annotations (Jobylon, etc.)
    for suffix in ["Öppnas i nytt fönster", "Opens in new window"]:
        if suffix in title:
            title = title.replace(suffix, "").strip()
    return title


def extract_city_from_dom(anchor):
    for element in [anchor.parent, anchor.parent.parent if anchor.parent else None]:
        if not element:
            continue
        for tag in element.find_all(True):
            classes = " ".join(tag.get("class", []))
            tag_id = tag.get("id", "")
            if LOCATION_CLASSES.search(classes) or LOCATION_CLASSES.search(tag_id):
                text = tag.get_text(strip=True)
                if text and len(text) < 36:
                    return text
    return None


def is_swedish_location(city_text):
    if not city_text:
        return True
    t = city_text.lower().strip().rstrip(",")
    if any(foreign in t for foreign in NON_SWEDISH_CITIES):
        return False
    # US state abbreviation: "City, TX" or "City, pa"
    parts = t.split(",")
    if len(parts) == 2 and parts[1].strip() in US_STATE_ABBREVS:
        return False
    if any(swedish in t for swedish in SWEDISH_CITIES):
        return True
    return True  # okänd plats – behåll


def parse_jobs_from_html(html, customer, base_url):
    soup = BeautifulSoup(html, "html.parser")
    patterns = get_patterns(customer)
    jobs = []
    seen_urls = set()
    skipped_abroad = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            base = base_url.split("/")[0] + "//" + base_url.split("/")[2]
            href = base + href
        if not href_matches(href, patterns) or href in seen_urls:
            continue

        raw_title = get_link_title(a).strip()
        if not raw_title or len(raw_title) <= 3:
            continue

        # For generic link texts, try to get the real title from ancestor element
        if raw_title.lower() in GENERIC_LINK_TEXTS:
            ancestor = get_ancestor_title(a)
            if ancestor:
                raw_title = ancestor
            else:
                continue

        # Skip remaining generic/navigation titles
        if raw_title.lower() in GENERIC_LINK_TEXTS:
            continue

        title = clean_title(raw_title)
        if not title or len(title) <= 3 or len(title) > 200:
            continue

        # Skip sentences/descriptions masquerading as titles
        t_lower = title.lower()
        if (title.endswith("?") or title.endswith("!")
                or t_lower.startswith("här hittar")
                or t_lower.startswith("this website")
                or t_lower.startswith("on this site")
                or t_lower.startswith("select which")
                or t_lower.startswith("få en notis")
                or t_lower.startswith("om du vill")
                or t_lower.startswith("var den första")
                or t_lower.startswith("we serve")
                or t_lower.startswith("meny")):
            continue
        # Skip titles with Lithuanian-specific diacritics (Swedbank Baltic jobs)
        if any(c in title for c in "ėųęąšžčĖŲĘĄŠŽČ"):
            continue
        # Skip address blocks (e.g. PostNord footer with postal codes)
        if re.search(r'\d{3}\s?\d{2}', title):
            continue

        raw_city = extract_city_from_dom(a) or extract_city_from_title(title)
        # Clean city: strip "Plats" prefix (ICA) and trailing comma/whitespace
        city = re.sub(r'^Plats', '', raw_city or '').strip().rstrip(',').strip() if raw_city else None

        if not is_swedish_location(city):
            skipped_abroad += 1
            continue

        # Also scan the full title for non-Swedish location names
        if not city and title_has_non_swedish_location(title):
            skipped_abroad += 1
            continue

        seen_urls.add(href)
        jobs.append({
            "id": href,
            "title": title,
            "url": href,
            "city": city or "",
            "blue_collar": is_blue_collar(title),
        })

    return jobs, skipped_abroad


def fetch_jobs_requests(customer):
    name = customer["name"]
    url = customer["url"]

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  ❌ Kunde inte hämta {name}: {e}")
        return []

    jobs, skipped = parse_jobs_from_html(resp.text, customer, url)
    msg = f"  → {name}: hittade {len(jobs)} annonser"
    if skipped:
        msg += f" ({skipped} utomlands filtrerade)"
    print(msg)
    return jobs


def fetch_jobs_playwright(customer):
    name = customer["name"]
    url = customer["url"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  ⚠️  Playwright ej installerat – faller tillbaka på requests för {name}")
        return fetch_jobs_requests(customer)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            try:
                page.goto(url, timeout=30000, wait_until="networkidle")
            except Exception:
                page.wait_for_timeout(8000)
            wait_selector = customer.get("wait_for_selector")
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(2000)
            content = page.content()
            browser.close()
    except Exception as e:
        print(f"  ❌ Playwright: Kunde inte hämta {name}: {e}")
        return []

    jobs, skipped = parse_jobs_from_html(content, customer, url)
    msg = f"  → {name}: hittade {len(jobs)} annonser (JS)"
    if skipped:
        msg += f" ({skipped} utomlands filtrerade)"
    print(msg)
    return jobs


def fetch_jobs(customer):
    if customer.get("use_playwright"):
        return fetch_jobs_playwright(customer)
    return fetch_jobs_requests(customer)


def find_new_jobs(customer_name, current_jobs, seen_cache, force=False):
    first_run = customer_name not in seen_cache
    previously_seen = set(seen_cache.get(customer_name, []))
    current_ids = {j["id"] for j in current_jobs}

    if force:
        return current_jobs, current_ids

    if first_run:
        print(f"  ℹ️  Första körningen – sparar {len(current_jobs)} annonser utan notis")
        return [], current_ids

    new_jobs = [j for j in current_jobs if j["id"] not in previously_seen]
    return new_jobs, current_ids


def format_job_line(j):
    city_part = f"  ({j['city']})" if j.get("city") else ""
    return f"     – {j['title']}{city_part}\n       {j['url']}"


def build_email_body(new_by_category):
    today = datetime.now().strftime("%Y-%m-%d")
    total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())
    lines = [
        f"Jobbannons-bevakning – {today}",
        f"Totalt {total} nya annonser",
        "",
    ]

    for category in ["Fokuskund", "KAM-kund"]:
        companies = new_by_category.get(category, {})
        if not companies:
            continue
        lines.append("=" * 40)
        lines.append(f"📌 {category.upper()}ER")
        lines.append("=" * 40)

        for company_name, jobs in sorted(companies.items()):
            lines.append(f"\n{company_name}")
            white = [j for j in jobs if not j["blue_collar"]]
            blue = [j for j in jobs if j["blue_collar"]]

            if white:
                lines.append("  👔 Tjänstemän:")
                for j in white:
                    lines.append(format_job_line(j))
            if blue:
                lines.append("  👷 Övriga:")
                for j in blue:
                    lines.append(format_job_line(j))

    lines += ["", "---", "Jobbannons-bevakaren (GitHub Actions)"]
    return "\n".join(lines)


def write_output(new_by_category):
    body = build_email_body(new_by_category)
    total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())
    today = datetime.now().strftime("%Y-%m-%d")

    with open("email_subject.txt", "w", encoding="utf-8") as f:
        f.write(f"Jobbbevakning {today} – {total} nya annonser")

    with open("email_body.txt", "w", encoding="utf-8") as f:
        f.write(body)

    print("\n📧 Mejlinnehåll sparat")


def main():
    force = "--force" in sys.argv
    if force:
        print("FORCE-läge: visar alla nuvarande jobb som nya\n")

    customers = load_json(CUSTOMERS_FILE)
    seen_cache = load_json(SEEN_JOBS_FILE)
    new_by_category = {}

    for customer in customers:
        name = customer["name"]
        category = customer.get("category", "KAM-kund")
        print(f"\nKollar {name}...")

        current_jobs = fetch_jobs(customer)
        if not current_jobs:
            continue

        new_jobs, current_ids = find_new_jobs(name, current_jobs, seen_cache, force=force)

        if new_jobs:
            print(f"  🆕 {len(new_jobs)} nya jobb!")
            for j in new_jobs:
                icon = "👷" if j["blue_collar"] else "👔"
                city_part = f" ({j['city']})" if j.get("city") else ""
                print(f"     {icon} {j['title']}{city_part}")
            new_by_category.setdefault(category, {})[name] = new_jobs
        else:
            print(f"  ✅ Inga nya jobb")

        seen_cache[name] = list(current_ids)

    save_json(SEEN_JOBS_FILE, seen_cache)
    print("\n💾 Cache sparad")

    if new_by_category:
        write_output(new_by_category)
    else:
        print("Inga nya annonser den här veckan")
        open("email_subject.txt", "w").close()
        open("email_body.txt", "w").close()


if __name__ == "__main__":
    main()
