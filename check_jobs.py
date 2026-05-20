import html as html_module
import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup, NavigableString, Tag, Comment
from datetime import datetime

CUSTOMERS_FILE = "customers.json"
COMPETITORS_FILE = "competitors.json"
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
    # Match when keyword starts a word boundary (not preceded by a letter).
    # Also allow camelCase suffixes like "locationName" (not followed by lowercase).
    # "place" excluded — too common in Tailwind utility classes (place-content-center etc.)
    r"(?<![a-zA-Z])(location|city|ort|stad|region|område)(?![a-z])", re.IGNORECASE
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
    # SJR generic CTA
    "läs mer och ansök",
    # Novare category labels (appear as anchor text on the job-listing page)
    "novare bemanning", "novare tech", "novare executive search",
    "novare interim & recruitment", "novare interim and recruitment",
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


def title_from_url_slug(href):
    """Extract a human-readable job title from a URL slug.

    Handles patterns like:
      /jobb/ekonomichef-till-seb-stockholm/          → "Ekonomichef till SEB Stockholm"
      /lediga-jobb/j/receptionist-till-nordstjernan/AYP12Q → "Receptionist till Nordstjernan"
      /jobb/controller_stockholm_uuid               → "Controller"
    """
    from urllib.parse import unquote
    try:
        path = unquote(href).rstrip("/")
        parts = [p for p in path.split("/") if p]
        # Walk from the end, skip short UUID-like segments
        for slug in reversed(parts):
            # Skip pure IDs (all digits or short hex-like) and known path-segment words
            if re.fullmatch(r'[A-Z0-9]{4,8}', slug):
                continue
            if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', slug):
                continue
            if slug.lower() in {"j", "jobs", "jobb", "sv", "lediga-jobb", "lediga_jobb"}:
                continue
            # Randstad pattern: "title_city_uuid" — strip trailing underscore-separated UUID
            slug = re.sub(r'_[0-9a-f-]{8,}$', '', slug)
            slug = re.sub(r'_[a-z]{2,12}_[0-9a-f-]{8,}$', '', slug)
            # Split on dashes (and underscores used as word separators)
            words = re.split(r'[-_]', slug)
            words = [w for w in words if w and not re.fullmatch(r'\d+', w)]
            if len(words) < 2:
                continue
            # Capitalize first word, keep rest as-is for proper nouns
            title = " ".join(w.capitalize() for w in words)
            if 5 < len(title) < 150:
                return title
    except Exception:
        pass
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
    # Normalize ALL-CAPS titles (e.g. Wise: "BUTIKSCHEF / AHLSELL / MÖLNDAL")
    # Only apply when >80% of letters are uppercase and title is >10 chars
    letters = [c for c in title if c.isalpha()]
    if len(letters) > 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8:
        # Capitalize each whitespace-separated token, preserve "/" and "-"
        title = " ".join(w.capitalize() for w in title.split())
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
                    # Skip text containing parentheses/brackets — these are role/category labels
                    # e.g. "IT-projektledare (deltid)Stockholm" from Teamtailor filter widgets
                    if re.search(r'[(){}\[\]]', text):
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
    # Orkla / Taleo: <span class="joblayouttoken-label">Job Posting City:</span><span>Malmö</span>
    for label_span in soup.find_all("span", class_="joblayouttoken-label"):
        if "job posting city" in label_span.get_text(strip=True).lower():
            city_span = label_span.find_next_sibling("span")
            if city_span:
                city = clean_city(city_span.get_text(strip=True))
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

        # Empty / too-short anchor text (e.g. Academic Work invisible overlay links)
        if not raw_title or len(raw_title) <= 3:
            ancestor = get_ancestor_title(a)
            if ancestor:
                raw_title = ancestor
            else:
                slug_title = title_from_url_slug(href)
                if slug_title:
                    raw_title = slug_title
                else:
                    continue

        # For generic link texts, try ancestor heading then URL slug
        if raw_title.lower() in GENERIC_LINK_TEXTS:
            ancestor = get_ancestor_title(a)
            if ancestor:
                raw_title = ancestor
            else:
                slug_title = title_from_url_slug(href)
                if slug_title:
                    raw_title = slug_title
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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
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


def build_email_body(new_by_category, competitor_jobs=None, customer_categories=None):
    """Build HTML email body.

    competitor_jobs: {customer_name: {competitor_name: [job_dict]}}
    customer_categories: {customer_name: category}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    competitor_jobs = competitor_jobs or {}
    customer_categories = customer_categories or {}

    own_total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())
    comp_total = sum(
        len(jobs)
        for by_comp in competitor_jobs.values()
        for jobs in by_comp.values()
    )
    total = own_total + comp_total

    h = []
    h.append('<!DOCTYPE html><html><head><meta charset="utf-8"></head>')
    h.append('<body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;color:#222;padding:16px;">')
    h.append(f'<p style="color:#888;font-size:13px;margin-bottom:2px;">Jobbannons-bevakning – {today}</p>')
    h.append(f'<h2 style="margin-top:0;">{total} nya annonser</h2>')

    # Collect all companies with any new jobs (own or competitor)
    all_companies = {}  # category -> set of company names
    for category, companies in new_by_category.items():
        for name in companies:
            all_companies.setdefault(category, set()).add(name)
    for cust_name, cat in customer_categories.items():
        if cust_name in competitor_jobs:
            all_companies.setdefault(cat, set()).add(cust_name)

    for category in ["Fokuskund", "KAM-kund"]:
        companies_in_cat = all_companies.get(category, set())
        if not companies_in_cat:
            continue
        h.append(f'<h3 style="background:#f4f4f4;padding:8px 12px;margin:28px 0 8px;border-left:4px solid #333;">📌 {category.upper()}ER</h3>')

        for company_name in sorted(companies_in_cat):
            h.append(f'<h4 style="margin:16px 0 4px;">{html_module.escape(company_name)}</h4>')

            # Own jobs
            own_jobs = new_by_category.get(category, {}).get(company_name, [])
            white = [j for j in own_jobs if not j["blue_collar"]]
            blue  = [j for j in own_jobs if j["blue_collar"]]
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

            # Competitor jobs
            by_comp = competitor_jobs.get(company_name, {})
            if by_comp:
                h.append('<p style="margin:12px 0 4px;font-weight:bold;">🔍 Via rekryteringsbolag</p>')
                for comp_name, jobs in sorted(by_comp.items()):
                    h.append(f'<p style="margin:2px 0 2px 12px;font-style:italic;color:#555;">{html_module.escape(comp_name)}</p>')
                    h.append('<ul style="margin:0 0 8px;padding-left:32px;">')
                    for j in jobs:
                        h.append(_job_li(j))
                    h.append('</ul>')

    h.append('<hr style="border:none;border-top:1px solid #ddd;margin-top:28px;">')
    h.append('<p style="color:#aaa;font-size:11px;text-align:center;">Jobbannons-bevakaren (GitHub Actions)</p>')
    h.append('</body></html>')
    return "\n".join(h)


def write_output(new_by_category, competitor_jobs=None, customer_categories=None):
    body = build_email_body(new_by_category, competitor_jobs, customer_categories)
    own_total = sum(len(jobs) for companies in new_by_category.values() for jobs in companies.values())
    comp_total = sum(
        len(jobs)
        for by_comp in (competitor_jobs or {}).values()
        for jobs in by_comp.values()
    )
    total = own_total + comp_total
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


def match_customer_for_competitor_job(href, title, customers):
    """Return matching customer if the job URL or title mentions one of our customers."""
    from urllib.parse import unquote
    slug = unquote(href).lower()
    title_lower = title.lower()
    for customer in customers:
        for term in customer.get("competitor_slugs", []):
            t = re.escape(term.lower())
            # URL: term as a whole slug-word bounded by / or -
            if re.search(r'(?:^|[-/])' + t + r'(?:[-/]|$)', slug):
                return customer
            # Title: term as a whole word (Swedish word boundary)
            if re.search(r'(?<![a-zåäö])' + t + r'(?![a-zåäö])', title_lower):
                return customer
    return None


def _fetch_jobs_from_sitemap(site):
    """Fetch all jobs by parsing the site's XML sitemap.

    Used when a competitor publishes all job URLs in their sitemap.xml.
    Titles are extracted from URL slugs via title_from_url_slug().
    Returns a list of job dicts [{id, title, url, city, blue_collar}].
    """
    sitemap_url = site["sitemap_url"]
    patterns = get_patterns(site)
    try:
        resp = requests.get(sitemap_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  Sitemap-fel ({site.get('name', sitemap_url)}): {e}")
        return []

    # Extract <loc> values — works without lxml
    loc_values = re.findall(r'<loc>\s*(https?://[^<\s]+)\s*</loc>', resp.text)
    jobs = []
    seen: set = set()
    for url in loc_values:
        if not href_matches(url, patterns):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = title_from_url_slug(url)
        if not title:
            continue
        jobs.append({
            "id":          url,
            "title":       clean_title(title),
            "url":         url,
            "city":        "",
            "blue_collar": is_blue_collar(title),
        })
    return jobs


def _fetch_intercepted_api_jobs(site):
    """Generic JSON API interceptor via Playwright, with optional GET pagination.

    Used for sites whose job data is returned in JSON responses intercepted via
    the browser's network layer.  Supports two modes:

    One-shot (default):
      Intercepts the first matching response and returns all jobs from it.

    Paginated GET (api_type == "paginated_get"):
      Intercepts the first response to learn the URL structure + grab cookies,
      then replays GET requests for subsequent pages until has_next_page=False
      or no jobs are returned.  Page param is incremented via "page=N" in the URL.

    Site config fields:
      api_intercept_url  – substring to match in response URL
      api_jobs_key       – key in JSON body containing the jobs list (default "jobs")
      api_title_key      – key within each job dict for the title (default "title")
      api_url_key        – key within each job dict for the job URL (default "url")
      api_city_key       – key within each job dict for city (default "municipality")
      api_type           – "paginated_get" enables multi-page GET pagination
    """
    try:
        from playwright.sync_api import sync_playwright
        import time as _time

        intercept = site["api_intercept_url"]
        jobs_key  = site.get("api_jobs_key",  "jobs")
        title_key = site.get("api_title_key", "title")
        url_key   = site.get("api_url_key",   "url")
        city_key  = site.get("api_city_key",  "municipality")
        paginated = site.get("api_type") == "paginated_get"

        # captured[0]: first intercepted raw URL (for pagination base)
        # captured[1]: cookies dict
        captured_url: list  = []
        captured_data: list = []
        cookies_dict: dict  = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pw_page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )

            def handle_response(response):
                if intercept in response.url and response.status == 200:
                    if not captured_url:
                        captured_url.append(response.url)
                    if not paginated:  # one-shot: collect all pages that fire
                        try:
                            data = response.json()
                            raw_jobs = data if isinstance(data, list) else data.get(jobs_key, [])
                            if raw_jobs and isinstance(raw_jobs[0], list):
                                raw_jobs = [j for sub in raw_jobs for j in sub]
                            captured_data.extend(raw_jobs)
                        except Exception:
                            pass

            pw_page.on("response", handle_response)
            try:
                pw_page.goto(site["url"], timeout=30000, wait_until="networkidle")
            except Exception:
                pw_page.wait_for_timeout(8000)
            pw_page.wait_for_timeout(4000)
            if paginated:
                cookies_dict = {c["name"]: c["value"] for c in pw_page.context.cookies()}
            browser.close()

        # --- Paginated GET mode ---
        if paginated:
            if not captured_url:
                print(f"  {site.get('name', '')}: API-anrop ej fångat")
                return []

            base_url = captured_url[0]
            session = requests.Session()
            ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            session.headers.update({"User-Agent": ua, "Accept": "application/json",
                                    "Referer": site["url"]})
            for c_name, c_val in cookies_dict.items():
                from urllib.parse import urlparse
                domain = urlparse(site["url"]).netloc
                session.cookies.set(c_name, c_val, domain=domain)

            page_num = 1
            while True:
                # Replace or append page=N in URL
                page_url = re.sub(r'\bpage=\d+', f'page={page_num}', base_url)
                if page_url == base_url and page_num > 1:
                    # No page param in URL — append it
                    sep = "&" if "?" in page_url else "?"
                    page_url = page_url + f"{sep}page={page_num}"
                if page_num > 1:
                    _time.sleep(0.3)
                try:
                    resp = session.get(page_url, timeout=15)
                    if not resp.content:
                        break
                    data = resp.json()
                    raw_jobs = data if isinstance(data, list) else data.get(jobs_key, [])
                    if raw_jobs and isinstance(raw_jobs[0], list):
                        raw_jobs = [j for sub in raw_jobs for j in sub]
                    if not raw_jobs:
                        break
                    captured_data.extend(raw_jobs)
                    # Stop if last page
                    if data.get("is_last_page") or not data.get("has_next_page"):
                        break
                    page_num += 1
                    if page_num > 20:  # safety cap
                        break
                except Exception as e:
                    print(f"  {site.get('name', '')} API sida {page_num}: {e}")
                    break

        # --- Build job dicts ---
        jobs = []
        seen: set = set()
        for job in captured_data:
            if not isinstance(job, dict):
                continue
            title = str(job.get(title_key, "")).strip()
            url_str = str(job.get(url_key, "")).strip()
            if not title:
                continue
            job_id = url_str or title
            if job_id in seen:
                continue
            seen.add(job_id)
            # City: try configured key, then fallback keys
            raw_city = (job.get(city_key) or job.get("city") or
                        job.get("location") or job.get("municipality") or "")
            # Some APIs return city as a list (e.g. Poolia municipality: ["Stockholm"])
            if isinstance(raw_city, list):
                raw_city = raw_city[0] if raw_city else ""
            jobs.append({
                "id":          job_id,
                "title":       clean_title(title),
                "url":         url_str,
                "city":        clean_city(str(raw_city).strip()),
                "blue_collar": is_blue_collar(title),
            })
        return jobs

    except Exception as e:
        print(f"  API-interceptor-fel ({site.get('name', '')}): {e}")
        return []


def _fetch_wp_rest_jobs(site):
    """Fetch jobs from a WordPress REST API endpoint (/wp-json/wp/v2/jobs).

    Makes plain GET requests (no Playwright needed — these endpoints are public).
    Paginates via X-WP-TotalPages header.

    Site config fields:
      api_wp_rest_url  – full URL to the WP REST endpoint
      api_per_page     – items per page (default 18)
      job_link_pattern – used for customer matching (unchanged)

    Title is taken from item["title"]["rendered"].
    URL is taken from item["link"].
    City is taken from item["acf"]["city"] if present.
    """
    import time as _time
    endpoint = site["api_wp_rest_url"]
    per_page = site.get("api_per_page", 18)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    jobs = []
    seen: set = set()
    page_num = 1
    total_pages = None

    while True:
        url = f"{endpoint}?per_page={per_page}&page={page_num}"
        try:
            resp = requests.get(url, timeout=15, headers=headers)
            if resp.status_code == 400:
                break  # WP returns 400 when page exceeds total
            resp.raise_for_status()
        except Exception as e:
            print(f"  {site.get('name', '')} WP REST sida {page_num}: {e}")
            break

        if total_pages is None:
            try:
                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            except Exception:
                total_pages = 1

        try:
            items = resp.json()
        except Exception as e:
            print(f"  {site.get('name', '')} WP REST JSON-fel: {e}")
            break

        if not items:
            break

        for item in items:
            if not isinstance(item, dict):
                continue
            # Title: nested in {"rendered": "..."}
            title_obj = item.get("title", {})
            title = (title_obj.get("rendered", "") if isinstance(title_obj, dict)
                     else str(title_obj)).strip()
            if not title:
                continue
            link = item.get("link", "").strip()
            if not link:
                continue
            if link in seen:
                continue
            seen.add(link)

            # City from ACF field
            acf = item.get("acf", {})
            city = clean_city(str(acf.get("city", "") or "").strip()) if isinstance(acf, dict) else ""

            jobs.append({
                "id":          link,
                "title":       clean_title(title),
                "url":         link,
                "city":        city,
                "blue_collar": is_blue_collar(title),
            })

        if page_num >= (total_pages or 1):
            break
        page_num += 1
        _time.sleep(0.2)  # polite pacing

    return jobs


def _fetch_adecco_jobs_via_api(site):
    """Fetch Adecco jobs by intercepting their internal JSON API via Playwright,
    then paginating through all pages via direct POST requests.

    Strategy:
    1. Open the page in Playwright once to capture the POST body + cookies.
    2. Replay the POST with range=0, 10, 20, … until no more jobs are returned.
    Returns a list of job dicts [{id, title, url, city, blue_collar}].
    """
    try:
        from playwright.sync_api import sync_playwright
        import urllib.parse as _up

        captured: dict = {}

        # --- Phase 1: capture initial POST body and cookies ---
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )

            def capture_request(request):
                intercept = site.get("api_intercept_url", "")
                if intercept and intercept in request.url and not captured.get("body"):
                    try:
                        captured["body"] = json.loads(request.post_data or "{}")
                    except Exception:
                        pass

            page.on("request", capture_request)
            try:
                page.goto(site["url"], timeout=30000, wait_until="networkidle")
            except Exception:
                page.wait_for_timeout(8000)
            page.wait_for_timeout(4000)
            captured["cookies"] = {c["name"]: c["value"] for c in page.context.cookies()}
            browser.close()

        if not captured.get("body"):
            print("  Adecco: kunde inte fånga API-anrop")
            return []

        # --- Phase 2: paginate via direct POST requests ---
        base_body = captured["body"]
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.adecco.com",
            "Referer": site["url"],
        })
        for c_name, c_val in captured["cookies"].items():
            session.cookies.set(c_name, c_val, domain="www.adecco.com")

        api_url   = f"https://www.adecco.com/api/data/jobs/summarized"
        collected = []
        seen_ids: set = set()
        page_size = 10  # Adecco returns 10 per request

        import time as _time
        for start in range(0, 500, page_size):  # cap at 500 to avoid runaway
            body = dict(base_body)
            body["range"] = start
            if start > 0:
                _time.sleep(0.5)  # polite pacing to avoid rate-limiting
            try:
                resp = session.post(api_url, json=body, timeout=15)
                if not resp.content:
                    break  # Empty response — end of results or session expired
                data = resp.json()
                jobs = data.get("jobs", [])
                if not jobs:
                    break  # No more results
                for job in jobs:
                    title = job.get("jobTitle", "").strip()
                    city  = clean_city(job.get("cityName", "").strip())
                    jid   = job.get("jobId", "")
                    apply = job.get("applyUri", "")
                    if not title:
                        continue
                    url_str = apply if apply else (
                        site["url"].rstrip("/") + "/" + _up.quote(str(jid))
                    )
                    if url_str in seen_ids:
                        continue
                    seen_ids.add(url_str)
                    collected.append({
                        "id":          url_str,
                        "title":       clean_title(title),
                        "url":         url_str,
                        "city":        city or "",
                        "blue_collar": is_blue_collar(title),
                    })
                # Check if we've reached the end
                total = data.get("pagination", {}).get("total", 0)
                if start + page_size >= total:
                    break
            except Exception as e:
                print(f"  Adecco API sida {start}: {e}")
                break

        return collected

    except Exception as e:
        print(f"  Adecco API-fel: {e}")
        return []


def _fetch_html_for_site(site, scroll_count=0, page_num=1):
    """Fetch rendered HTML for a site dict (has 'url' and optional 'use_playwright').

    scroll_count: number of scroll-to-bottom cycles to perform after initial load.
    page_num: page number for URL-based pagination (default 1 = first page).
      If page_num > 1 the URL is modified:
        - existing "page=N" param is incremented, OR
        - "?page=N" / "&page=N" is appended
    """
    # Sites with a JSON API interception use a dedicated fetcher
    if site.get("api_intercept_url"):
        return None  # Signal to caller to use _fetch_adecco_jobs_via_api instead
    url = site["url"]
    if page_num > 1:
        page_param = site.get("page_param", "page")  # e.g. "paged" for WordPress
        param_pattern = re.compile(rf'\b{re.escape(page_param)}=\d+')
        if param_pattern.search(url):
            url = param_pattern.sub(f'{page_param}={page_num}', url)
        elif "?" in url:
            url = url + f"&{page_param}={page_num}"
        else:
            url = url + f"?{page_param}={page_num}"
    if site.get("use_playwright"):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                try:
                    page.goto(url, timeout=30000, wait_until="networkidle")
                except Exception:
                    page.wait_for_timeout(8000)
                wait_selector = site.get("wait_for_selector")
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=10000)
                    except Exception:
                        pass
                    # Extra grace period so the full initial batch renders
                    page.wait_for_timeout(1500)
                else:
                    page.wait_for_timeout(2000)
                # Scroll to trigger infinite-scroll / lazy-load pagination
                for i in range(scroll_count):
                    try:
                        prev_height = page.evaluate("document.body.scrollHeight")
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1500)
                        new_height = page.evaluate("document.body.scrollHeight")
                        # Stop early if the page stopped growing (all jobs loaded)
                        if new_height == prev_height and i >= 2:
                            break
                    except Exception:
                        break
                try:
                    html = page.content()
                except Exception:
                    page.wait_for_timeout(3000)
                    try:
                        html = page.content()
                    except Exception as e2:
                        print(f"  Playwright-fel ({site.get('name', url)}): page.content: {e2}")
                        browser.close()
                        return None
                browser.close()
                return html
        except Exception as e:
            print(f"  Playwright-fel ({site.get('name', url)}): {e}")
            return None
    else:
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  Requests-fel ({site.get('name', url)}): {e}")
            return None


def fetch_all_competitor_jobs(competitors, customers):
    """Scrape competitor sites and match jobs to our customers.

    Returns: {customer_name: {competitor_name: [job_dict, ...]}}
    """
    result = {}

    for competitor in competitors:
        comp_name = competitor["name"]
        print(f"\nScannar {comp_name}...")

        # Route to correct fetcher based on site config
        if competitor.get("sitemap_url"):
            all_jobs = _fetch_jobs_from_sitemap(competitor)
        elif competitor.get("api_wp_rest_url"):
            all_jobs = _fetch_wp_rest_jobs(competitor)
        elif competitor.get("api_intercept_url") and competitor.get("api_type") == "adecco_post":
            all_jobs = _fetch_adecco_jobs_via_api(competitor)
        elif competitor.get("api_intercept_url"):
            all_jobs = _fetch_intercepted_api_jobs(competitor)
        else:
            # Use a high scroll count to load as many jobs as possible via infinite scroll.
            # Default 10 scrolls (~100–150 extra jobs on Teamtailor); override per site.
            scroll_count = competitor.get("scroll_count", 10)
            max_pages  = competitor.get("max_pages", 1)

            all_jobs = []
            seen_job_ids: set = set()

            for page_num in range(1, max_pages + 1):
                html = _fetch_html_for_site(competitor, scroll_count=scroll_count, page_num=page_num)
                if not html:
                    break
                page_jobs, _ = parse_jobs_from_html(html, competitor, competitor["url"])
                new_jobs = [j for j in page_jobs if j["id"] not in seen_job_ids]
                if not new_jobs and page_num > 1:
                    break  # Page returned nothing new — we've reached the end
                all_jobs.extend(new_jobs)
                seen_job_ids.update(j["id"] for j in new_jobs)

            # Fetch city for jobs missing it (same as regular flow)
            for job in all_jobs:
                if not job["city"]:
                    fetched = fetch_city_for_job(job["url"])
                    job["city"] = clean_city(fetched) if fetched else ""

        matched_count = 0
        for job in all_jobs:
            customer = match_customer_for_competitor_job(job["url"], job["title"], customers)
            if not customer:
                continue
            cust_name = customer["name"]
            matched_count += 1
            job["competitor"] = comp_name
            result.setdefault(cust_name, {}).setdefault(comp_name, []).append(job)

        print(f"  → {comp_name}: {matched_count} kundmatchningar")

    return result


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
    customer_categories = {c["name"]: c.get("category", "KAM-kund") for c in customers}
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

    # --- Konkurrentscanning ---
    new_competitor_jobs = {}  # {customer_name: {competitor_name: [jobs]}}
    try:
        competitors = load_json(COMPETITORS_FILE)
    except Exception:
        competitors = []

    if competitors:
        print("\n" + "="*50)
        print("KONKURRENTSÖKNING")
        print("="*50)

        competitor_first_run = "_konkurrenter" not in seen_cache
        seen_competitor_ids = set(seen_cache.get("_konkurrenter", []))

        all_matches = fetch_all_competitor_jobs(competitors, customers)
        all_new_competitor_ids = []

        for cust_name, by_comp in all_matches.items():
            for comp_name, jobs in by_comp.items():
                if competitor_first_run or force:
                    # Första körningen: spara allt men skicka inget (om ej force)
                    all_new_competitor_ids.extend(j["id"] for j in jobs)
                    if force:
                        new_competitor_jobs.setdefault(cust_name, {})[comp_name] = jobs
                else:
                    new_jobs = [j for j in jobs if j["id"] not in seen_competitor_ids]
                    if new_jobs:
                        all_new_competitor_ids.extend(j["id"] for j in new_jobs)
                        new_competitor_jobs.setdefault(cust_name, {})[comp_name] = new_jobs
                        print(f"  🆕 {comp_name} → {cust_name}: {len(new_jobs)} nya")

        if competitor_first_run and not force:
            total_found = sum(len(j) for by_comp in all_matches.values() for j in by_comp.values())
            print(f"  ℹ️  Första konkurrentkörningen – sparar {total_found} annonser utan notis")

        seen_cache["_konkurrenter"] = list(seen_competitor_ids | set(all_new_competitor_ids))

    save_json(SEEN_JOBS_FILE, seen_cache)
    print("\n💾 Cache sparad")

    has_own = bool(new_by_category)
    has_competitor = bool(new_competitor_jobs)

    if has_own or has_competitor:
        write_output(new_by_category, new_competitor_jobs, customer_categories)
    else:
        print("Inga nya annonser den här veckan")
        open("email_subject.txt", "w").close()
        open("email_body.txt", "w").close()


if __name__ == "__main__":
    main()
