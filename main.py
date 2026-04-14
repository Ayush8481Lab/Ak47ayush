from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

# 1. FIXED CORS MIDDLEWARE
# allow_credentials MUST be False when allow_origins is set to "*" (All Domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # <--- This fixes the "specific domains" issue!
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "My Custom Pathfinder Spotify API is running perfectly!"}

@app.get("/search")
def search_spotify(q: str, token: str, limit: int = 10, tp: str = None):
    try:
        url = "https://api-partner.spotify.com/pathfinder/v2/query"

        # The exact payload we extracted
        payload = {
            "variables": {
                "searchTerm": "Drake", 
                "offset": 0,
                "limit": 10,           
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

        # DYNAMIC INJECTION
        payload["variables"]["searchTerm"] = q
        payload["variables"]["limit"] = limit

        # CRITICAL: Web Player headers
        headers = {
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Request the data!
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            return {
                "error": "Spotify rejected the Pathfinder request.",
                "status_code": response.status_code,
                "details": response.text
            }
            
        data = response.json()
        
        # 2. RAW DATA FEATURE: If the URL has &tp=or, return the EXACT original Spotify response
        if tp == "or":
            return data
        
        # 3. Clean Data Extraction (Default)
        results =[]
        try:
            items = data.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items",[])
            
            for item in items:
                track = item.get("item", {}).get("data", {})
                if not track:
                    continue
                    
                images = track.get("albumOfTrack", {}).get("coverArt", {}).get("sources",[])
                image_url = images[0]["url"] if images else None
                
                # FIX: Extract ALL artists and separate them with a comma
                artists = track.get("artists", {}).get("items",[])
                artist_names =[a.get("profile", {}).get("name") for a in artists if a.get("profile", {}).get("name")]
                artist_name_string = ", ".join(artist_names) if artist_names else "Unknown"

                track_uri = track.get("uri", "")
                track_id = track_uri.split(":")[-1] if track_uri else ""
                
                results.append({
                    "song_name": track.get("name", "Unknown"),
                    "artist": artist_name_string,  # Now returns "Artist 1, Artist 2"
                    "spotify_url": f"https://open.spotify.com/track/{track_id}" if track_id else None,
                    "image": image_url
                })
        except Exception as parse_error:
            return {"error": "Failed to parse GraphQL structure.", "details": str(parse_error), "raw_data": data}
            
        return {"search_query": q, "results": results}
        
    except Exception as e:
        return {"error": "Server error", "details": str(e)}
