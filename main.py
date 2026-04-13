from fastapi import FastAPI
import requests
import json
import urllib.parse

app = FastAPI()

@app.get("/")
def home():
    return {"message": "My Custom Pathfinder Spotify API is running perfectly!"}

@app.get("/search")
def search_spotify(q: str, token: str, limit: int = 10):
    try:
        # 1. Pathfinder requires GraphQL variables
        variables = {
            "searchTerm": q,
            "offset": 0,
            "limit": limit,
            "numberOfTopResults": 5,
            "includeAudiobooks": False
        }
        
        # 2. Pathfinder requires the Persisted Query Hash (Spotify's web search signature)
        extensions = {
            "persistedQuery": {
                "version": 1,
                # Note: This is a recent hash. If Spotify updates their web app and you get a "PersistedQueryNotFound" error,
                # just go to your Network log, click the "query?operationName=searchDesktop" request, and copy the new sha256Hash from the URL!
                "sha256Hash": "1301151626db4eaeecea0b1e4c935eeae304fcd2b58e6e584988dc8241076b32"
            }
        }

        # 3. Build the complex Pathfinder URL
        url = (
            f"https://api-partner.spotify.com/pathfinder/v2/query"
            f"?operationName=searchDesktop"
            f"&variables={urllib.parse.quote(json.dumps(variables))}"
            f"&extensions={urllib.parse.quote(json.dumps(extensions))}"
        )

        # 4. CRITICAL: Inject strict Web Player headers to bypass the 429 Bot Protection
        headers = {
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/"
        }
        
        # 5. Request data from Spotify Partner API (Bypasses CORS & 429!)
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return {
                "error": "Spotify rejected the Pathfinder request.",
                "status_code": response.status_code,
                "details": response.text
            }
            
        data = response.json()
        
        # 6. Extract data from Pathfinder's deeply nested GraphQL tree
        results =[]
        
        try:
            # Navigate the GraphQL tree structure
            items = data.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items",[])
            
            for item in items:
                track = item.get("item", {}).get("data", {})
                if not track:
                    continue
                    
                # Extract High-Res Cover Art
                images = track.get("albumOfTrack", {}).get("coverArt", {}).get("sources",[])
                image_url = images[0]["url"] if images else None
                
                # Extract Artist Name
                artists = track.get("artists", {}).get("items", [])
                artist_name = artists[0].get("profile", {}).get("name") if artists else "Unknown"

                # Extract Spotify URL
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
