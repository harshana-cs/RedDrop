import requests

def get_hospital_coordinates(hospital_name, district):
    query = f"{hospital_name}, {district}, Nepal"

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": query,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "RedDrop-Blood-System"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print("Location fetch error:", e)

    return None, None
