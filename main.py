from fastapi import FastAPI
import requests

app = FastAPI()

@app.get("/")
def home():
    return {"message": "My Custom Pathfinder Spotify API is running perfectly!"}

@app.get("/search")
def search_spotify(q: str, token: str, limit: int = 10):
    try:
        url = "https://api-partner.spotify.com/pathfinder/v2/query"

        # 1. THE PERFECT PAYLOAD: 
        # This is the exact lock and key you just extracted!
        payload = {
            "variables": {
                "searchTerm": "Drake", # This will be replaced dynamically
                "offset": 0,
                "limit": 10,           # This will be replaced dynamically
                "numberOfTopResults": 5,
                "includeAudiobooks": True,
                "includeArtistHasConcertsField": False,
                "includePreReleases": True,
                "includeAuthors": False,
                "includeEpisodeContentRatingsV2": False
            },
            "operationName": "searchDesktop",
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "21b3fe49546912ba782db5c47e9ef5a7dbd20329520ba0c7d0fcfadee671d24e"
                }
            }
        }

        # 2. DYNAMIC INJECTION:
        # We silently swap "Drake" with whatever the user actually searched for (q).
        payload["variables"]["searchTerm"] = q
        payload["variables"]["limit"] = limit

        # 3. CRITICAL: Inject strict Web Player headers
        headers = {
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # 4. Request the data!
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            return {
                "error": "Spotify rejected the Pathfinder request.",
                "status_code": response.status_code,
                "details": response.text
            }
            
        data = response.json()
        
        # 5. Extract the clean data for your mobile app
        results =[]
        try:
            items = data.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items",[])
            
            for item in items:
                track = item.get("item", {}).get("data", {})
                if not track:
                    continue
                    
                images = track.get("albumOfTrack", {}).get("coverArt", {}).get("sources", [])
                image_url = images[0]["url"] if images else None
                
                artists = track.get("artists", {}).get("items",[])
                artist_name = artists[0].get("profile", {}).get("name") if artists else "Unknown"

                track_uri = track.get("uri", "")
                track_id = track_uri.split(":")[-1] if track_uri else ""
                
                results.append({
                    "song_name": track.get("name", "Unknown"),
                    "artist": artist_name,
                    "spotify_url": f"https://open.spotify.com/track/{track_id}" if track_id else None,
                    "image": image_url
                })
        except Exception as parse_error:
            return {"error": "Failed to parse GraphQL structure.", "details": str(parse_error), "raw_data": data}
            
        return {"search_query": q, "results": results}
        
    except Exception as e:
        return {"error": "Server error", "details": str(e)}
