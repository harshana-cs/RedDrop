import requests
import logging

logger = logging.getLogger(__name__)

BAATO_API_KEY = "bpk.s14kxOCujL2LX83sLDvVnhp0kKMumPjr0QvhNeJVCuz8"

# ============================================================
# STATIC COORDINATES — All Nepal hospitals
# Keys are (hospital_name_lowercase, district_lowercase)
# ============================================================
STATIC_HOSPITAL_COORDS = {

    # ── Koshi Province ──────────────────────────────────────
    ("bayalpata hospital",                        "achham"):        (29.0697,  81.3580),
    ("mechi zonal hospital",                      "jhapa"):         (26.6436,  87.8978),
    ("b&c hospital",                              "jhapa"):         (26.6300,  87.8700),
    ("birta city hospital",                       "jhapa"):         (26.6200,  87.8600),
    ("koshi hospital",                            "morang"):        (26.4756,  87.2773),
    ("birat medical college",                     "morang"):        (26.4600,  87.2600),
    ("nobel medical college",                     "morang"):        (26.4900,  87.2800),
    ("dharan b.p. koirala institute of health sciences", "sunsari"): (26.8125, 87.2836),
    ("bp koirala institute of health sciences",   "sunsari"):       (26.8125,  87.2836),
    ("dhankuta hospital",                         "dhankuta"):      (26.9833,  87.3333),
    ("bhojpur district hospital",                 "bhojpur"):       (27.1742,  87.0527),
    ("ilam district hospital",                    "ilam"):          (26.9083,  87.9267),
    ("panchthar district hospital",               "panchthar"):     (27.1500,  87.7833),
    ("taplejung district hospital",               "taplejung"):     (27.3500,  87.6667),
    ("terhathum district hospital",               "terhathum"):     (27.1167,  87.5500),
    ("sankhuwasabha district hospital",           "sankhuwasabha"): (27.3500,  87.2333),
    ("solukhumbu district hospital",              "solukhumbu"):    (27.5333,  86.7167),
    ("khotang district hospital",                 "khotang"):       (27.0500,  86.8333),
    ("okhaldhunga community hospital",            "okhaldhunga"):   (27.3167,  86.5000),
    ("udayapur district hospital",                "udayapur"):      (26.9333,  86.5333),

    # ── Madhesh Province ───────────────────────────────────
    ("janakpur zonal hospital",                   "dhanusha"):      (26.7288,  85.9280),
    ("janaki medical college",                    "dhanusha"):      (26.7167,  85.9333),
    ("jaleshwar hospital",                        "mahottari"):     (26.6500,  85.7833),
    ("siraha district hospital",                  "siraha"):        (26.6500,  86.2000),
    ("saptari district hospital",                 "saptari"):       (26.5833,  86.7500),
    ("kalaiya hospital",                          "bara"):          (27.0400,  84.9950),
    ("narayani hospital",                         "parsa"):         (27.0167,  84.8667),
    ("gaur hospital",                             "rautahat"):      (26.7667,  85.2833),
    ("sarlahi district hospital",                 "sarlahi"):       (26.9667,  85.5833),

    # ── Bagmati Province ───────────────────────────────────
    ("bir hospital",                              "kathmandu"):     (27.7041,  85.3145),
    ("teaching hospital",                         "kathmandu"):     (27.7333,  85.3333),
    ("tribhuvan university teaching hospital",    "kathmandu"):     (27.7333,  85.3333),
    ("grande international hospital",             "kathmandu"):     (27.6762,  85.3240),
    ("norvic international hospital",             "kathmandu"):     (27.6939,  85.3157),
    ("civil hospital",                            "kathmandu"):     (27.7167,  85.3500),
    ("nepal medical college",                     "kathmandu"):     (27.7286,  85.3922),
    ("nepal korea friendship hospital",           "kathmandu"):     (27.7200,  85.3400),
    ("hams hospital",                             "kathmandu"):     (27.7028,  85.3141),
    ("mulpani nagar hospital",                    "kathmandu"):     (27.7300,  85.4000),
    ("nepal orthopaedic hospital",                "kathmandu"):     (27.7000,  85.3200),
    ("shankarapur hospital",                      "kathmandu"):     (27.7500,  85.3800),
    ("om hospital & research centre",             "kathmandu"):     (27.7028,  85.3141),
    ("medicare hospital",                         "kathmandu"):     (27.7167,  85.3167),
    ("kathmandu model hospital",                  "kathmandu"):     (27.7000,  85.3333),
    ("national trauma center",                    "kathmandu"):     (27.7041,  85.3145),
    ("patan hospital",                            "lalitpur"):      (27.6667,  85.3167),
    ("b&b hospital",                              "lalitpur"):      (27.6605,  85.3215),
    ("alka hospital",                             "lalitpur"):      (27.6552,  85.3240),
    ("nepal mediciti hospital",                   "lalitpur"):      (27.6389,  85.3019),
    ("bhaktapur hospital",                        "bhaktapur"):     (27.6726,  85.4277),
    ("korea nepal friendship hospital",           "bhaktapur"):     (27.6800,  85.4300),
    ("nagarik hospital",                          "bhaktapur"):     (27.6710,  85.4298),
    ("sushma koirala memorial hospital",          "bhaktapur"):     (27.6833,  85.4167),
    ("dhulikhel hospital",                        "kavrepalanchok"): (27.6236, 85.5456),
    ("bharatpur hospital",                        "chitwan"):       (27.6833,  84.4333),
    ("chitwan medical college",                   "chitwan"):       (27.6794,  84.4322),
    ("b.p. koirala memorial cancer hospital",     "chitwan"):       (27.6747,  84.4397),
    ("hetauda hospital",                          "makwanpur"):     (27.4167,  85.0333),
    ("dhading hospital",                          "dhading"):       (27.8667,  84.9167),
    ("trishuli district hospital",                "nuwakot"):       (27.9333,  85.1667),
    ("rasuwa district hospital",                  "rasuwa"):        (28.1000,  85.3667),
    ("sindhuli district hospital",                "sindhuli"):      (27.2500,  85.9667),
    ("ramechhap district hospital",               "ramechhap"):     (27.3167,  86.0833),
    ("dolakha district hospital",                 "dolakha"):       (27.6667,  86.1667),
    ("sindhupalchok district hospital",           "sindhupalchok"): (27.9500,  85.6833),

    # ── Gandaki Province ───────────────────────────────────
    ("gandaki medical college",                   "kaski"):         (28.2380,  83.9956),
    ("fewa city hospital",                        "kaski"):         (28.2167,  83.9667),
    ("manipal teaching hospital",                 "kaski"):         (28.2167,  84.0000),
    ("western regional hospital",                 "kaski"):         (28.2096,  83.9856),
    ("gorkha district hospital",                  "gorkha"):        (28.0000,  84.6333),
    ("lamjung district hospital",                 "lamjung"):       (28.1333,  84.3833),
    ("damauli district hospital",                 "tanahun"):       (27.9167,  84.2333),
    ("syangja district hospital",                 "syangja"):       (27.9500,  83.8833),
    ("baglung district hospital",                 "baglung"):       (28.2667,  83.5833),
    ("dhaulagiri zonal hospital",                 "baglung"):       (28.2667,  83.5833),
    ("parbat district hospital",                  "parbat"):        (28.2333,  83.6833),
    ("myagdi district hospital",                  "myagdi"):        (28.3167,  83.4833),
    ("mustang district hospital",                 "mustang"):       (28.9833,  83.8333),
    ("manang district hospital",                  "manang"):        (28.6667,  84.0167),
    ("nawalpur district hospital",                "nawalpur"):      (27.7000,  84.1167),

    # ── Lumbini Province ──────────────────────────────────
    ("lumbini provincial hospital",               "rupandehi"):     (27.7000,  83.4500),
    ("universal college hospital",                "rupandehi"):     (27.6833,  83.4333),
    ("crimson hospital",                          "rupandehi"):     (27.5167,  83.4667),
    ("lumbini medical college",                   "palpa"):         (27.8667,  83.5500),
    ("gulmi district hospital",                   "gulmi"):         (28.0667,  83.2667),
    ("arghakhanchi district hospital",            "arghakhanchi"):  (27.9500,  83.1500),
    ("kapilvastu district hospital",              "kapilvastu"):    (27.5667,  83.0333),
    ("parasi district hospital",                  "parasi"):        (27.7833,  83.7667),
    ("rapti provincial hospital",                 "dang"):          (28.0833,  82.3000),
    ("pyuthan district hospital",                 "pyuthan"):       (28.1000,  82.8667),
    ("rolpa district hospital",                   "rolpa"):         (28.2167,  82.6500),
    ("rukum east district hospital",              "eastern rukum"): (28.6167,  82.6167),
    ("nepalgunj medical college",                 "banke"):         (28.0500,  81.6167),
    ("bheri hospital",                            "banke"):         (28.0500,  81.6167),
    ("bardiya district hospital",                 "bardiya"):       (28.3333,  81.4167),

    # ── Karnali Province ──────────────────────────────────
    ("karnali academy of health sciences",        "jumla"):         (29.2833,  82.1667),
    ("birendranagar provincial hospital",         "surkhet"):       (28.6000,  81.6333),
    ("dailekh district hospital",                 "dailekh"):       (28.8500,  81.7167),
    ("jajarkot district hospital",                "jajarkot"):      (28.7000,  82.1833),
    ("kalikot district hospital",                 "kalikot"):       (29.1500,  81.6333),
    ("salyan district hospital",                  "salyan"):        (28.3667,  82.1667),
    ("dolpa district hospital",                   "dolpa"):         (29.3000,  82.8000),
    ("humla district hospital",                   "humla"):         (29.9667,  81.8167),
    ("mugu district hospital",                    "mugu"):          (29.5833,  82.1500),
    ("rukum west district hospital",              "rukum west"):    (28.6167,  82.3667),

    # ── Sudurpashchim Province ────────────────────────────
    ("seti provincial hospital",                  "kailali"):       (28.6833,  80.6000),
    ("mahakali hospital",                         "kanchanpur"):    (29.0000,  80.1167),
    ("dadeldhura hospital",                       "dadeldhura"):    (29.3000,  80.5833),
    ("baitadi district hospital",                 "baitadi"):       (29.5333,  80.4167),
    ("darchula district hospital",                "darchula"):      (29.8500,  80.5500),
    ("bajhang district hospital",                 "bajhang"):       (29.5500,  81.1833),
    ("bajura district hospital",                  "bajura"):        (29.4500,  81.5000),
    ("doti district hospital",                    "doti"):          (29.2667,  80.9333),
}

# In-memory cache — avoids repeat API calls per server session
_COORD_CACHE: dict = {}


def _normalize(text: str) -> str:
    return text.strip().lower()


def _try_static(hospital_name: str, district: str):
    key = (_normalize(hospital_name), _normalize(district))
    return STATIC_HOSPITAL_COORDS.get(key)


def _try_baato(hospital_name: str, district: str):
    query = f"{hospital_name}, {district}, Nepal"
    try:
        response = requests.get(
            "https://api.baato.io/api/v1/search",
            params={"q": query, "key": BAATO_API_KEY, "limit": 1},
            timeout=10
        )
        if response.status_code == 403:
            logger.warning(
                "Baato 403 — add your backend server IP to "
                "Baato dashboard → API Keys → allowlist."
            )
            return None
        response.raise_for_status()
        data    = response.json()
        records = data.get("data") or []
        if not records:
            return None
        first    = records[0]
        centroid = first.get("centroid") or {}
        lat      = centroid.get("lat") or first.get("lat")
        lon      = centroid.get("lon") or first.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except Exception as e:
        logger.error("Baato error for '%s, %s': %s", hospital_name, district, e)
    return None


def _try_nominatim(hospital_name: str, district: str):
    queries = [
        f"{hospital_name}, {district}, Nepal",
        f"{hospital_name}, Nepal",
        f"{hospital_name} hospital, Nepal",
    ]
    headers = {"User-Agent": "RedDrop-BloodSystem/1.0 (contact@reddrop.com)"}
    for q in queries:
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "np"},
                headers=headers,
                timeout=10
            )
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            logger.error("Nominatim error for '%s': %s", q, e)
    return None


def get_coordinates(hospital_name: str, district: str = "") -> tuple:
    """
    Main geocoding function.

    Priority:
      1. Memory cache  — instant, avoids repeat lookups
      2. Static table  — instant, covers all hospitals in the system
      3. Baato.io      — Nepal-specific (needs IP whitelisted in Baato dashboard)
      4. Nominatim     — free OSM fallback, no key required

    Returns (lat, lon) or (None, None) if all sources fail.

    Usage:
        from hospital.geocoding import get_coordinates
        lat, lon = get_coordinates("Nagarik Hospital", "Bhaktapur")
    """
    cache_key = (_normalize(hospital_name), _normalize(district))

    if cache_key in _COORD_CACHE:
        return _COORD_CACHE[cache_key]

    result = _try_static(hospital_name, district)
    if result:
        logger.info("Coords [static]: %s, %s → %s", hospital_name, district, result)
        _COORD_CACHE[cache_key] = result
        return result

    result = _try_baato(hospital_name, district)
    if result:
        logger.info("Coords [Baato]: %s, %s → %s", hospital_name, district, result)
        _COORD_CACHE[cache_key] = result
        return result

    result = _try_nominatim(hospital_name, district)
    if result:
        logger.info("Coords [Nominatim]: %s, %s → %s", hospital_name, district, result)
        _COORD_CACHE[cache_key] = result
        return result

    logger.warning(
        "No coords found for '%s, %s'. "
        "Add it to STATIC_HOSPITAL_COORDS in geocoding.py",
        hospital_name, district
    )
    _COORD_CACHE[cache_key] = (None, None)
    return None, None


# Backward-compatible alias
def get_coordinates_from_osm(hospital_name: str, district: str = "") -> tuple:
    return get_coordinates(hospital_name, district)