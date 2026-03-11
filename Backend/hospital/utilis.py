import requests

def get_coordinates_from_osm(hospital_name, district):
    query = f"{hospital_name}, {district}, Nepal"

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": query,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "RedDrop-BloodSystem"
    }

    response = requests.get(url, params=params, headers=headers)

    data = response.json()

    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])

    return None, None