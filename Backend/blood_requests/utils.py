import requests

BAATO_API_KEY = "bpk.s14kxOCujL2LX83sLDvVnhp0kKMumPjr0QvhNeJVCuz8"

def get_coordinates_from_osm(hospital_name, district):

    query = f"{hospital_name}, {district}, Nepal"

    url = "https://api.baato.io/api/v1/search"

    params = {
        "q": query,
        "key": BAATO_API_KEY,
        "limit": 1,
        "type": "hospital"  # optional: filters results to hospitals only
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None, None

    records = data.get("data") or []
    if not records:
        return None, None

    first = records[0]
    centroid = first.get("centroid") or {}

    lat = centroid.get("lat")
    lon = centroid.get("lon")

    if lat is None or lon is None:
        point = first.get("point") or {}
        lat = point.get("lat")
        lon = point.get("lon")

    if lat is None or lon is None:
        lat = first.get("lat")
        lon = first.get("lon")

    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None

    return None, None
