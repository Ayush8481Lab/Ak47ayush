const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "*",
};

const COMMON_HEADERS = (token: string) => ({
  "Authorization": `Bearer ${token}`,
  "App-Platform": "WebPlayer",
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  "Origin": "https://open.spotify.com",
  "Referer": "https://open.spotify.com/",
  "Accept": "application/json",
  "Content-Type": "application/json",
  "Accept-Encoding": "gzip, deflate, br"
});

const _normalize_uri = (id: string, prefix: string) => id.startsWith("spotify:") ? id : `spotify:${prefix}:${id}`;

// Fetch helper (Returns raw stream for 0-latency forwarding)
async function _queryPathfinderStream(opName: string, shaHash: string, variables: any, token: string) {
  const payload = {
    variables, operationName: opName,
    extensions: { persistedQuery: { version: 1, sha256Hash: shaHash } }
  };
  return fetch("https://api-partner.spotify.com/pathfinder/v2/query", {
    method: "POST",
    headers: COMMON_HEADERS(token),
    body: JSON.stringify(payload)
  });
}

// Fetch helper (Returns parsed JSON for data manipulation)
async function _queryPathfinderJson(opName: string, shaHash: string, variables: any, token: string) {
  const res = await _queryPathfinderStream(opName, shaHash, variables, token);
  if (!res.ok) throw new Error(`Spotify rejected ${opName}: ${res.status}`);
  return res.json();
}

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS_HEADERS });

    const url = new URL(request.url);
    const path = url.pathname;
    const token = url.searchParams.get("token") || "";

    try {
      // ==========================================
      // 1. SEARCH ENDPOINT
      // ==========================================
      if (path === "/search") {
        if (!token) throw new Error("Missing token");
        const q = url.searchParams.get("q") || "";
        const tp = url.searchParams.get("tp");

        const data: any = await _queryPathfinderJson(
          "searchDesktop", 
          "658888f28f397bca282c3b31ab745708fbf39b8b7780baefa57d95a0973ad5a9",
          { searchTerm: q, offset: 0, limit: 10, numberOfTopResults: 5, includeAudiobooks: true, includeArtistHasConcertsField: false, includePreReleases: true, includeAuthors: false, includeEpisodeContentRatingsV2: false },
          token
        );

        if (tp === "or") {
          return Response.json(data, { headers: { ...CORS_HEADERS, "Cache-Control": "public, s-maxage=60" } });
        }

        const results = [];
        const items = data?.data?.searchV2?.tracksV2?.items || [];
        for (const item of items) {
          const track = item?.item?.data;
          if (!track) continue;
          
          const images = track?.albumOfTrack?.coverArt?.sources || [];
          const artists = track?.artists?.items || [];
          const track_uri = track?.uri || "";

          results.append({
            song_name: track?.name || "Unknown",
            artist: artists.map((a: any) => a?.profile?.name).join(", ") || "Unknown",
            spotify_url: track_uri ? `https://open.spotify.com/track/${track_uri.split(":").pop()}` : null,
            image: images.length > 0 ? images[0].url : null
          });
        }
        return Response.json({ search_query: q, results }, { headers: { ...CORS_HEADERS, "Cache-Control": "public, s-maxage=60" } });
      }

      // ==========================================
      // 2. THE ULTIMATE TRACK ENDPOINT
      // ==========================================
      if (path === "/track") {
        if (!token) throw new Error("Missing token");
        const id = url.searchParams.get("id") || "";
        const clean_id = id.split(":").pop() || "";

        // 🔥 OPTIMIZATION: Fetch Track Info & Radio ID simultaneously!
        const [track_data, radio_res] = await Promise.all([
          _queryPathfinderJson("getTrack", "612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294", { uri: _normalize_uri(id, "track") }, token).catch(() => null),
          fetch(`https://spclient.wg.spotify.com/inspiredby-mix/v2/seed_to_playlist/spotify:track:${clean_id}?response-format=json`, { headers: COMMON_HEADERS(token) }).catch(() => null)
        ]);

        let radio_id = null;
        let radio_uri = null;
        let radio_contents = null;

        if (radio_res && radio_res.ok) {
          const radioData: any = await radio_res.json();
          const mediaItems = radioData?.mediaItems || [];
          radio_uri = mediaItems.length > 0 ? mediaItems[0].uri : null;
          radio_id = radio_uri ? radio_uri.split(":").pop() : null;
        }

        if (radio_uri) {
          radio_contents = await _queryPathfinderJson("fetchPlaylistContents", "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4", { uri: radio_uri, offset: 0, limit: 50, includeEpisodeContentRatingsV2: true }, token).catch(() => null);
        }

        return Response.json({ radio_id, track_response: track_data, radio_playlist_contents: radio_contents }, { headers: CORS_HEADERS });
      }

      // ==========================================
      // 3. ZERO-LATENCY DIRECT STREAMING ENDPOINTS
      // ==========================================
      // Because these endpoints just return Spotify's exact response, 
      // we STREAM the bytes directly to the user for absolute 0-latency overhead!
      const streamingRoutes: Record<string, any> = {
        "/track/recommendations": ["internalLinkRecommenderTrack", "c77098ee9d6ee8ad3eb844938722db60570d040b49f41f5ec6e7be9160a7c86b", "track"],
        "/track/similar-albums": ["similarAlbumsBasedOnThisTrack", "1d1f93a737498adca2c892c73af87fc0b052afe4e1a33c989540c32413dfae17", "track"],
        "/track/artists": ["queryTrackArtists", "ee2b038198f5e62c679c3996584d9249bbee55fe69fc212271c56492a022c798", "track"],
        "/playlist": ["fetchPlaylistMetadata", "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4", "playlist"],
        "/playlist/contents": ["fetchPlaylistContents", "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4", "playlist"],
        "/playlist/permissions": ["playlistPermissions", "f4c99a92059b896b9e4e567403abebe666c0625a36286f9c2bb93961374a75c6", "playlist"]
      };

      if (streamingRoutes[path]) {
        if (!token) throw new Error("Missing token");
        const id = url.searchParams.get("id") || "";
        const [opName, sha, prefix] = streamingRoutes[path];
        
        let variables: any = { uri: _normalize_uri(id, prefix) };
        if (path === "/playlist" || path === "/playlist/contents") {
          variables = { ...variables, offset: 0, limit: 50, enableWatchFeedEntrypoint: false, includeEpisodeContentRatingsV2: true };
        }

        const upstreamResponse = await _queryPathfinderStream(opName, sha, variables, token);
        return new Response(upstreamResponse.body, { status: upstreamResponse.status, headers: { ...CORS_HEADERS, "Content-Type": "application/json" }});
      }

      // Default home
      return Response.json({ message: "My Ultra-Fast Hybrid API is running!" }, { headers: CORS_HEADERS });

    } catch (error: any) {
      return Response.json({ error: "Server error", details: error.message }, { status: 500, headers: CORS_HEADERS });
    }
  }
}
