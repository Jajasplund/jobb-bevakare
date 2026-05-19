import html as html_module
import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup, NavigableString, Tag, Comment
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
    "stenungsund", "eslöv", "vetlanda", "charlottenberg", "åmål", "storlien",
    "halland", "skåne", "dalarna", "värmland", "blekinge",
    "remote", "distans", "hybridarbete", "hybrid", "hela sverige", "hela landet", "sverige", "sweden",
}

NON_SWEDISH_CITIES = {
    "oslo", "bergen", "trondheim", "stavanger",
    "köpenhamn", "copenhagen", "aarhus", "odense", "denmark",
    "helsinki", "helsingfors", "tampere", "finland",
    "norway", "norge",
    "london", "berlin", "hamburg", "amsterdam", "paris",
    "warsaw", "warszawa", "riga", "tallinn", "vilnius", "vilniuje", "panevežys", "panevėžyje",
    "kaunas", "klaipėda", "šiauliai",
    "tartu", "pärnu", "narva",
    "ventspils", "liepāja", "daugavpils", "jelgava", "jūrmala",
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
    "anchor", "anchor anchor",
}

# Location terms that are valid for filtering but not useful as displayed city
ABSTRACT_LOCATIONS = {
    "hybridarbete", "hybrid", "remote", "distans",
    "hela sverige", "hela landet", "sverige", "sweden",
}

# Known UI/accessibility artifacts that should never be treated as job titles
TITLE_ARTIFACTS = {"anchor", "#", "↑", "▲", "»", "›"}


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
    # Last word(s) match a known Swedish city: "Servicetekniker Helsingborg"
    words = title.split()
    for n in (2, 1):
        if len(words) >= n + 1:
            candidate = " ".join(words[-n:])
            if candidate.lower() in SWEDISH_CITIES:
                return candidate
    return None


def title_has_non_swedish_location(title):
    t = title.lower()
    return any(city in t for city in NON_SWEDISH_CITIES)


def _direct_text(tag):
    """Return only the direct (non-nested) text of a tag, ignoring child elements and HTML comments."""
    return "".join(str(c) for c in tag.children
                   if isinstance(c, NavigableString) and not isinstance(c, Comment)).strip()


def get_link_title(anchor):
    """Extract job title from a link element, handling multiple site structures.

    Priority order:
    0. title attribute on span/div (Teamtailor: <span title="Clean Job Title">...)
    1. Direct text nodes of heading (avoids sibling dept/company spans)
    2. First child element of heading (Teamtailor: <h3><span>Title</span><span>Dept</span></h3>)
    3. Full heading text with separator (last resort)
    4. Title-class elements
    5. Direct text nodes of anchor (ICA: <a><span aria>anchor</span>Real title text</a>)
    6. Full anchor text
    """
    # 0. title attribute on span/div — Teamtailor renders clean title here
    #    e.g. <span class="... hyphens-auto" title="Erfaren Frontendutvecklare till Svea Bank">
    for tag in anchor.find_all(["span", "div"]):
        title_attr = tag.get("title", "").strip()
        if title_attr and 5 < len(title_attr) < 200 and title_attr.lower() not in TITLE_ARTIFACTS:
            return title_attr

    for tag in anchor.find_all(["h2", "h3", "h4", "strong"]):
        # 1. Direct text nodes only — skips nested dept/company spans
        direct = _direct_text(tag)
        if direct and len(direct) > 5 and direct.lower() not in TITLE_ARTIFACTS:
            return direct
        # 2. First child element — for <h3><span>Title</span><span>Dept</span></h3>
        for child in tag.children:
            if isinstance(child, Tag):  # Tag only, not NavigableString
                child_text = _direct_text(child) or child.get_text(strip=True)
                if child_text and len(child_text) > 5 and child_text.lower() not in TITLE_ARTIFACTS:
                    return child_text
                break  # only try first child element
        # 3. Full heading text with space separator
        full = tag.get_text(" ", strip=True)
        if full and len(full) > 5 and full.lower() not in TITLE_ARTIFACTS:
            return full
    # 4. Elements with title-related CSS classes
    for tag in anchor.find_all(True):
        classes = " ".join(tag.get("class", []))
        if re.search(r'title|heading|job.?name|position.?name', classes, re.IGNORECASE):
            text = _direct_text(tag) or tag.get_text(strip=True)
            if text and 5 < len(text) < 200 and text.lower() not in TITLE_ARTIFACTS:
                return text
    # 5. Direct text of the anchor itself (ICA: title is a text node after accessibility spans)
    direct = _direct_text(anchor)
    if direct and len(direct) > 5 and direct.lower() not in TITLE_ARTIFACTS:
        return direct
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
                    # Skip CamelCase-concatenated text (title+city merged, e.g. "ExamensarbeteSödertälje")
                    if re.search(r'[a-zåäö][A-ZÅÄÖ]', text):
                        continue
                    return text
    return None


def clean_city(text):
    if not text:
        return text
    # Strip Swedish county prefix: "Stockholms län, Ekerö" → "Ekerö"
    text = re.sub(r'^[A-ZÅÄÖ][a-zåäö]+s? [lL]än,\s*', '', text).strip()
    # Strip leading label word (e.g. "locationStockholm" → "Stockholm")
    text = re.sub(r'^[a-z]+', '', text).strip()
    # Strip country code + rest: "Södertälje, SE, 151 65" → "Södertälje"
    text = re.sub(r',\s*[A-Z]{2}[\s,].*$', '', text).strip()
    # Strip standalone postal codes at end
    text = re.sub(r',?\s*\d{3}\s?\d{2}\s*$', '', text).strip()
    return text.rstrip(",").strip()


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


def fetch_city_for_job(url):
    """Fetch individual job page and extract city — used as fallback when listing page has no city."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None
    # Teamtailor detail pages: <dt>Platser</dt><dd>Stockholm</dd>
    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).lower()
        if label in ("platser", "plats", "location", "locations", "ort"):
            dd = dt.find_next_sibling("dd")
            if dd:
                city = clean_city(dd.get_text(strip=True))
                if city and 1 < len(city) < 40:
                    return city
    # JSON-LD structured data (JobPosting schema)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                loc = data.get("jobLocation", {})
                if isinstance(loc, dict):
                    addr = loc.get("address", {})
                    if isinstance(addr, dict):
                        city = addr.get("addressLocality", "")
                        if city:
                            return clean_city(city)
        except Exception:
            pass
    # Schema.org microdata — high confidence
    for tag in soup.find_all(attrs={"itemprop": "addressLocality"}):
        text = clean_city(tag.get_text(strip=True))
        if text and len(text) < 40:
            return text
    # Elements with location-related classes or ids — only return known Swedish cities
    for tag in soup.find_all(True):
        classes = " ".join(tag.get("class", []))
        tag_id = tag.get("id", "")
        if LOCATION_CLASSES.search(classes) or LOCATION_CLASSES.search(tag_id):
            text = clean_city(tag.get_text(strip=True))
            if text and 2 < len(text) < 40 and text.lower() in SWEDISH_CITIES:
                return text
    return None


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

        full_anchor_text = a.get_text(" ", strip=True)
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

        # --- City extraction ---
        # Strategy: collect a geographic city (non-abstract) first; fall back to abstract
        # (e.g. "Hybridarbete") only if nothing better is found.
        abstract_fallback = None

        def _accept_city(candidate):
            """Return (is_geographic, is_abstract) for a candidate city string."""
            # Normalize: strip trailing punctuation/whitespace before comparing
            cl = candidate.lower().strip().rstrip(".,; ")
            if cl in ABSTRACT_LOCATIONS:
                return False, True
            # Accept any Swedish city OR unknown short string (kept for unknown municipalities)
            return True, False

        # 1. ICA: city in data-ph-at-job-location-text="Kungälv"
        raw_city = a.get("data-ph-at-job-location-text", "").strip() or None
        if raw_city:
            geo, abst = _accept_city(raw_city)
            if abst:
                abstract_fallback = raw_city
                raw_city = None

        # 2. St1 / similar: city in anchor's own title="City ● Category"
        if not raw_city:
            a_title_attr = a.get("title", "").strip()
            if a_title_attr and "●" in a_title_attr:
                candidate = a_title_attr.split("●")[0].strip()
                if candidate and 1 < len(candidate) < 35:
                    geo, abst = _accept_city(candidate)
                    if abst:
                        abstract_fallback = abstract_fallback or candidate
                    else:
                        raw_city = candidate

        # 3. DOM extraction (location-class elements in parent)
        if not raw_city:
            dom_city = extract_city_from_dom(a)
            if dom_city:
                geo, abst = _accept_city(dom_city)
                if abst:
                    abstract_fallback = abstract_fallback or dom_city
                else:
                    raw_city = dom_city

        # 4. City embedded in title text ("till Stockholm", "i Göteborg", last word)
        if not raw_city:
            title_city = extract_city_from_title(title)
            if title_city:
                geo, abst = _accept_city(title_city)
                if abst:
                    abstract_fallback = abstract_fallback or title_city
                elif title_city.lower() in SWEDISH_CITIES:
                    raw_city = title_city

        # 5. Teamtailor "Title · Dept · City" pattern in full anchor text
        if not raw_city and "·" in full_anchor_text:
            dot_parts = [p.strip() for p in full_anchor_text.split("·")]
            for part in reversed(dot_parts[1:]):
                candidate = part.split(",")[0].strip()
                if candidate and 1 < len(candidate) < 35 and candidate[:1].isupper():
                    if candidate.lower() in SWEDISH_CITIES:
                        geo, abst = _accept_city(candidate)
                        if abst:
                            abstract_fallback = abstract_fallback or candidate
                        else:
                            raw_city = candidate
                            break

        # 6. <p> tag inside anchor (Teamtailor card: <p>Dept · City</p>)
        if not raw_city:
            for p_tag in a.find_all("p"):
                p_text = p_tag.get_text(strip=True)
                for seg in reversed([s.strip() for s in p_text.split("·")]):
                    candidate = seg.split(",")[0].strip()
                    if candidate and len(candidate) < 35 and candidate[:1].isupper():
                        if candidate.lower() in SWEDISH_CITIES:
                            geo, abst = _accept_city(candidate)
                            if abst:
                                abstract_fallback = abstract_fallback or candidate
                            else:
                                raw_city = candidate
                                break
                if raw_city:
                    break

        # 7. URL slug — case-insensitive (Toyota uses lowercase slugs, Orkla uses mixed)
        if not raw_city:
            try:
                from urllib.parse import unquote
                url_words = re.findall(r'[a-zA-ZåäöÅÄÖ]+', unquote(href.split("?")[0]))
                for word in reversed(url_words):
                    if word.lower() in SWEDISH_CITIES and word.lower() not in ABSTRACT_LOCATIONS:
                        raw_city = word[0].upper() + word[1:]
                        break
            except Exception:
                pass

        # Fall back to abstract location (e.g. "Hybridarbete") if no geographic city found
        if not raw_city and abstract_fallback:
            raw_city = abstract_fallback

        # Clean city: strip "Plats" prefix (ICA), label prefixes, postal codes
        city = clean_city(re.sub(r'^Plats', '', raw_city or '').strip()) if raw_city else None

        if not is_swedish_location(city):
            skipped_abroad += 1
            continue

        # Also scan the full title for non-Swedish location names
        if not city and title_has_non_swedish_location(title):
            skipped_abroad += 1
            continue

        # Use customer-level default city as last resort (e.g. Kammarkollegiet → Stockholm)
        if not city:
            city = customer.get("default_city", "") or ""

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
    for job in jobs:
        if not job["city"]:
            fetched = fetch_city_for_job(job["url"])
            job["city"] = clean_city(fetched) if fetched else ""
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
    for job in jobs:
        if not job["city"]:
            fetched = fetch_city_for_job(job["url"])
            job["city"] = clean_city(fetched) if fetched else ""
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


def _job_li(j):
    title = html_module.escape(j["title"])
    url = html_module.escape(j["url"])
    city = f' <span style="color:#666;font-size:13px;">({html_module.escape(j["city"])})</span>' if j.get("city") else ""
    return f'<li style="margin-bottom:4px;"><a href="{url}" style="color:#0055cc;">{title}</a>{city}</li>'


def build_email_body(new_by_category):
    today = datetime.now().strftime("%Y-%m-%d")
    total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())

    h = []
    h.append('<!DOCTYPE html><html><head><meta charset="utf-8"></head>')
    h.append('<body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;color:#222;padding:16px;">')
    h.append(f'<p style="color:#888;font-size:13px;margin-bottom:2px;">Jobbannons-bevakning – {today}</p>')
    h.append(f'<h2 style="margin-top:0;">{total} nya annonser</h2>')

    for category in ["Fokuskund", "KAM-kund"]:
        companies = new_by_category.get(category, {})
        if not companies:
            continue
        h.append(f'<h3 style="background:#f4f4f4;padding:8px 12px;margin:28px 0 8px;border-left:4px solid #333;">📌 {category.upper()}ER</h3>')

        for company_name, jobs in sorted(companies.items()):
            h.append(f'<h4 style="margin:16px 0 4px;">{html_module.escape(company_name)}</h4>')
            white = [j for j in jobs if not j["blue_collar"]]
            blue = [j for j in jobs if j["blue_collar"]]
            if white:
                h.append('<p style="margin:4px 0;font-weight:bold;">👔 Tjänstemän</p>')
                h.append('<ul style="margin:0 0 8px;padding-left:20px;">')
                for j in white:
                    h.append(_job_li(j))
                h.append('</ul>')
            if blue:
                h.append('<p style="margin:4px 0;font-weight:bold;">👷 Övriga</p>')
                h.append('<ul style="margin:0 0 8px;padding-left:20px;">')
                for j in blue:
                    h.append(_job_li(j))
                h.append('</ul>')

    h.append('<hr style="border:none;border-top:1px solid #ddd;margin-top:28px;">')
    h.append('<p style="color:#aaa;font-size:11px;text-align:center;">Jobbannons-bevakaren (GitHub Actions)</p>')
    h.append('</body></html>')
    return "\n".join(h)


def write_output(new_by_category):
    body = build_email_body(new_by_category)
    total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())
    today = datetime.now().strftime("%Y-%m-%d")

    with open("email_subject.txt", "w", encoding="utf-8") as f:
        f.write(f"Jobbbevakning {today} – {total} nya annonser")

    with open("email_body.txt", "w", encoding="utf-8") as f:
        f.write(body)

    print("\n📧 Mejlinnehåll sparat")


def debug_company(customer):
    """Dump raw HTML for the first 3 job anchors — used to diagnose title/city issues."""
    from urllib.parse import unquote as _unquote
    name = customer["name"]
    print(f"\n{'='*60}")
    print(f"DEBUG: {name}  (playwright={customer.get('use_playwright', False)})")
    print(f"URL: {customer['url']}")
    print(f"{'='*60}")

    if customer.get("use_playwright"):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                try:
                    page.goto(customer["url"], timeout=30000, wait_until="networkidle")
                except Exception:
                    page.wait_for_timeout(8000)
                if customer.get("wait_for_selector"):
                    try:
                        page.wait_for_selector(customer["wait_for_selector"], timeout=10000)
                    except Exception:
                        pass
                else:
                    page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
        except Exception as e:
            print(f"Playwright-fel: {e}")
            return
    else:
        try:
            resp = requests.get(customer["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
        except Exception as e:
            print(f"Requests-fel: {e}")
            return

    soup = BeautifulSoup(html, "html.parser")
    patterns = get_patterns(customer)
    found = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            base = customer["url"].split("/")[0] + "//" + customer["url"].split("/")[2]
            href = base + href
        if not href_matches(href, patterns):
            continue
        found += 1
        if found > 3:
            break
        print(f"\n--- Ankare {found}: {href} ---")
        print(f"Rå HTML:\n{a}\n")
        print(f"get_link_title()  = {repr(get_link_title(a))}")
        print(f"get_text()        = {repr(a.get_text(strip=True)[:120])}")
        print(f"_direct_text(a)   = {repr(_direct_text(a)[:120])}")
        print(f"data-location     = {repr(a.get('data-ph-at-job-location-text', ''))}")
        for tag in a.find_all(["span", "div"]):
            t_attr = tag.get("title", "")
            if t_attr:
                print(f"  title-attr on <{tag.name}>: {repr(t_attr[:100])}")
        headings = a.find_all(["h2", "h3", "h4", "strong"])
        for h in headings:
            print(f"  <{h.name}> direct='{_direct_text(h)[:80]}'  full='{h.get_text(strip=True)[:80]}'")
        for p in a.find_all("p"):
            print(f"  <p> text='{p.get_text(strip=True)[:80]}'")

    if found == 0:
        print("Inga matchande ankare hittades — kontrollera job_link_pattern")


def main():
    force = "--force" in sys.argv
    if force:
        print("FORCE-läge: visar alla nuvarande jobb som nya\n")

    # Debug-läge: python check_jobs.py --debug "Adda"
    debug_args = [a for a in sys.argv if a.startswith("--debug")]
    if debug_args:
        debug_name = sys.argv[sys.argv.index(debug_args[0]) + 1] if len(sys.argv) > sys.argv.index(debug_args[0]) + 1 else ""
        customers = load_json(CUSTOMERS_FILE)
        matches = [c for c in customers if debug_name.lower() in c["name"].lower()]
        if not matches:
            print(f"Hittade inget bolag som matchar '{debug_name}'")
            print("Tillgängliga: " + ", ".join(c["name"] for c in customers))
        for c in matches:
            debug_company(c)
        return

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
