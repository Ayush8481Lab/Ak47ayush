from fastapi import FastAPI
import requests

app = FastAPI()

@app.get("/")
def home():
    return {"message": "My Custom Pass-Through Spotify API is running perfectly!"}

@app.get("/search")
def search_spotify(q: str, token: str, CID: str = None, limit: int = 10):
    try:
        # 1. Prepare the Spotify search URL
        url = f"https://api.spotify.com/v1/search?q={q}&type=track&limit={limit}"
        
        # 2. Inject YOUR token from the URL into the hidden backend headers
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        # 3. Request data from Spotify from the Vercel server (Bypasses CORS!)
        response = requests.get(url, headers=headers)
        
        # If the token is invalid or expired, tell the user exactly why
        if response.status_code != 200:
            return {
                "error": "Spotify rejected the token.",
                "status_code": response.status_code,
                "details": response.text
            }
            
        data = response.json()
        tracks = data.get("tracks", {}).get("items",[])
        
        # 4. Clean up the response for your mobile app
        results =[]
        for item in tracks:
            # Safely grab the album cover image if it exists
            images = item.get("album", {}).get("images", [])
            image_url = images[0]["url"] if images else None
            
            results.append({
                "song_name": item["name"],
                "artist": item["artists"][0]["name"],
                "spotify_url": item["external_urls"]["spotify"],
                "image": image_url
            })
            
        return {"search_query": q, "results": results}
        
    except Exception as e:
        return {"error": "Server error", "details": str(e)}
