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


@app.get("/search")
async def search_spotify(q: str, token: str, response: Response, limit: int = 10, offset: int = 0, tp: str = None):
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"

    try:
        url = "https://api-partner.spotify.com/pathfinder/v2/query"

        payload = {
            "variables": {
                "searchTerm": q, 
                "offset": offset, 
                "limit": limit,           
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
                    "sha256Hash": "658888f28f397bca282c3b31ab745708fbf39b8b7780baefa57d95a0973ad5a9"
                }
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br" 
        }
        
        res = await client.post(url, json=payload, headers=headers)
        
        if res.status_code != 200:
            response.headers["Cache-Control"] = "no-store"
            return {
                "error": "Spotify rejected the Pathfinder request.",
                "status_code": res.status_code,
                "details": res.text
            }
            
        data = res.json()
        
        if tp == "or":
            return data
        
        results = []
        try:
            items = data.get("data", {}).get("searchV2", {}).get("tracksV2", {}).get("items", [])
            
            for item in items:
                track = item.get("item", {}).get("data", {})
                if not track:
                    continue
                    
                images = track.get("albumOfTrack", {}).get("coverArt", {}).get("sources", [])
                image_url = images[0]["url"] if images else None
                
                artists = track.get("artists", {}).get("items", [])
                artist_names = [a.get("profile", {}).get("name") for a in artists if a.get("profile", {}).get("name")]
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
            
        return {"search_query": q, "results": results}
        
    except Exception as e:
        response.headers["Cache-Control"] = "no-store"
        return {"error": "Server error", "details": str(e)}


# =====================================================================
# INTERNAL HELPER & NEW INTERCEPTED FEATURES (DO NOT TOUCH ABOVE)
# =====================================================================

def _normalize_uri(id_or_uri: str, prefix: str) -> str:
    """Smart helper: Lets users pass either '4qnFfsCa...' OR 'spotify:track:4qnFfsCa...'"""
    return id_or_uri if id_or_uri.startswith("spotify:") else f"spotify:{prefix}:{id_or_uri}"


async def _query_pathfinder(op_name: str, sha_hash: str, variables: dict, token: str, response: Response):
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
    url = "https://api-partner.spotify.com/pathfinder/v2/query"
    
    payload = {
        "variables": variables,
        "operationName": op_name,
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha_hash}}
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "App-Platform": "WebPlayer",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://open.spotify.com",
        "Referer": "https://open.spotify.com/",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate, br"
    }
    try:
        res = await client.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            response.headers["Cache-Control"] = "no-store"
            return {"error": f"Spotify rejected {op_name}", "status": res.status_code, "details": res.text}
        return res.json() # Returns original raw JSON as requested
    except Exception as e:
        response.headers["Cache-Control"] = "no-store"
        return {"error": "Server error", "details": str(e)}


# 1. GET TRACK (Metadata & live Stream Count)
@app.get("/track")
async def get_track(id: str, token: str, response: Response):
    return await _query_pathfinder(
        op_name="getTrack",
        sha_hash="612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294",
        variables={"uri": _normalize_uri(id, "track")},
        token=token, response=response
    )


# 2. GET PLAYLIST METADATA & TRACKS
@app.get("/playlist")
async def get_playlist(id: str, token: str, response: Response, offset: int = 0, limit: int = 100):
    return await _query_pathfinder(
        op_name="fetchPlaylistMetadata",
        sha_hash="a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4",
        variables={
            "uri": _normalize_uri(id, "playlist"),
            "offset": offset,
            "limit": limit,
            "enableWatchFeedEntrypoint": False
        },
        token=token, response=response
    )


# 3. GET RECOMMENDED RELATED TRACKS (Based on a single song)
@app.get("/track/recommendations")
async def get_track_recommendations(id: str, token: str, response: Response, limit: int = 5):
    return await _query_pathfinder(
        op_name="internalLinkRecommenderTrack",
        sha_hash="c77098ee9d6ee8ad3eb844938722db60570d040b49f41f5ec6e7be9160a7c86b",
        variables={"uri": _normalize_uri(id, "track"), "limit": limit},
        token=token, response=response
    )


# 4. GET SIMILAR ALBUMS (Based on a single song)
@app.get("/track/similar-albums")
async def get_similar_albums(id: str, token: str, response: Response, limit: int = 50, albums_only: bool = True):
    return await _query_pathfinder(
        op_name="similarAlbumsBasedOnThisTrack",
        sha_hash="1d1f93a737498adca2c892c73af87fc0b052afe4e1a33c989540c32413dfae17",
        variables={"uri": _normalize_uri(id, "track"), "limit": limit, "albumsOnly": albums_only},
        token=token, response=response
    )
