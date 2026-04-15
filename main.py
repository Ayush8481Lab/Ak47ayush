from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()

# FIXED CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LATENCY FIX 1: GLOBAL CONNECTION POOL
# This keeps the TCP/TLS connection open to Spotify between requests,
# shaving off ~150ms-250ms of handshake time per search.
client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
    timeout=5.0
)

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

@app.get("/")
def home():
    return {"message": "My Ultra-Fast Pathfinder API is running!"}

# LATENCY FIX 2: Added "async def" and the "Response" object for caching
# ADDED: "page" parameter (defaults to 1)
@app.get("/search")
async def search_spotify(q: str, token: str, response: Response, limit: int = 10, page: int = 1, tp: str = None):
    # LATENCY FIX 3: EDGE CACHING
    # Vercel will cache the result for 60 seconds. If users search the same song, 
    # Vercel bypasses Python entirely and returns the data in ~1 millisecond.
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"

    # DYNAMIC OFFSET CALCULATION
    # Ensure page is at least 1 so we never get a negative offset
    safe_page = max(1, page)
    calculated_offset = (safe_page - 1) * limit

    try:
        url = "https://api-partner.spotify.com/pathfinder/v2/query"

        payload = {
            "variables": {
                "searchTerm": q, # Dynamically injected right here
                "offset": calculated_offset, # Dynamically injected here based on page & limit
                "limit": limit,  # Dynamically injected right here         
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

        # CRITICAL: Web Player headers (Added Accept-Encoding for faster compressed data transfer)
        headers = {
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br" # Tells Spotify to zip the data (much faster download)
        }
        
        # LATENCY FIX 4: Asynchronous network request
        res = await client.post(url, json=payload, headers=headers)
        
        if res.status_code != 200:
            # If there's an error, don't cache it!
            response.headers["Cache-Control"] = "no-store"
            return {
                "error": "Spotify rejected the Pathfinder request.",
                "status_code": res.status_code,
                "details": res.text
            }
            
        data = res.json()
        
        # RAW DATA FEATURE
        if tp == "or":
            return data
        
        # Clean Data Extraction
        results =[]
        try:
            items = data.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items",[])
            
            for item in items:
                track = item.get("item", {}).get("data", {})
                if not track:
                    continue
                    
                images = track.get("albumOfTrack", {}).get("coverArt", {}).get("sources",[])
                image_url = images[0]["url"] if images else None
                
                # EXTRACT ALL ARTISTS (Comma separated)
                artists = track.get("artists", {}).get("items",[])
                artist_names =[a.get("profile", {}).get("name") for a in artists if a.get("profile", {}).get("name")]
                artist_name_string = ", ".join(artist_names) if artist_names else "Unknown"

                track_uri = track.get("uri", "")
                track_id = track_uri.split(":")[-1] if track_uri else ""
                
                results.append({
                    "song_name": track.get("name", "Unknown"),
                    "artist": artist_name_string,
                    "spotify_url": f"https://open.spotify.com/track/{track_id}" if track_id else None,
                    "image": image_url
                })
        except Exception as parse_error:
            return {"error": "Failed to parse GraphQL structure.", "details": str(parse_error), "raw_data": data}
            
        # Optional: I included "current_page" in the final return so your frontend knows what page it is on
        return {"search_query": q, "current_page": safe_page, "results": results}
        
    except Exception as e:
        response.headers["Cache-Control"] = "no-store"
        return {"error": "Server error", "details": str(e)}
