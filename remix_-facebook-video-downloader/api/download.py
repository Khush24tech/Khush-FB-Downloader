from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from urllib.parse import urlparse
import yt_dlp
import requests
import os

app = FastAPI()

class VideoRequest(BaseModel):
    url: str

@app.post("/api/get_info")
async def get_video_info(data: VideoRequest):
    url = data.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
        
    # Basic URL validation for Facebook domains
    is_fb = any(domain in url.lower() for domain in ["facebook.com", "fb.watch", "fb.com", "fb.gg"])
    if not is_fb:
        raise HTTPException(status_code=400, detail="Please provide a valid Facebook, Reels, or Watch URL")

    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get('url')
            
            if not video_url and 'formats' in info:
                playable_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') != 'none' and f.get('ext') == 'mp4']
                if playable_formats:
                    playable_formats.sort(key=lambda x: (x.get('height', 0)), reverse=True)
                    video_url = playable_formats[0].get('url')
            
            if not video_url:
                raise Exception("Could not extract a direct playable stream link.")
                
            return {
                "success": True,
                "title": info.get('title', 'facebook_video'),
                "video_url": video_url
            }
    except Exception as e:
        error_msg = str(e)
        if "Sign in" in error_msg or "login" in error_msg.lower():
            detail = "This video is private or requires login. Only public Facebook videos can be downloaded."
        elif "unsupported url" in error_msg.lower():
            detail = "Please provide a valid Facebook, Reels, or Watch URL."
        else:
            detail = f"Failed to extract video: {error_msg}"
        raise HTTPException(status_code=400, detail=detail)

@app.get("/api/proxy_stream")
async def proxy_stream(stream_url: str):
    try:
        # Parse the incoming URL to check its domain
        parsed_url = urlparse(stream_url)
        allowed_domains = ["fbcdn.net", "facebook.com", "instagram.com"]
        
        # Verify the domain ends with an allowed host
        if not any(parsed_url.netloc.endswith(domain) for domain in allowed_domains):
            raise HTTPException(status_code=403, detail="Access denied: Invalid stream source.")
            
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(stream_url, headers=headers, stream=True)
        
        # Check Content-Length header (in bytes). 50MB = 50 * 1024 * 1024
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > 52428800:
            raise HTTPException(status_code=413, detail="Video file is too large for the free tier.")
        
        def generate_file():
            for chunk in response.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

        return StreamingResponse(
            generate_file(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'attachment; filename="facebook_video.mp4"',
                "Cache-Control": "no-cache",
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Proxy Failed: {str(e)}")

# Static files mount for local runtime serving /public directory
if os.path.exists("public"):
    app.mount("/static", StaticFiles(directory="public"), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def read_index():
        return FileResponse("public/index.html")
