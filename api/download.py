from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse, Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from urllib.parse import urlparse
import yt_dlp
import requests
import os
import re

app = FastAPI()

class VideoRequest(BaseModel):
    url: str

    @field_validator('url')
    @classmethod
    def sanitize_and_validate_url(cls, v: str) -> str:
        v = v.strip()
        dangerous_patterns = [r"<script>", r"javascript:", r"exec\(", r"eval\(", r"__import__", r"os\.system"]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Malicious or unauthorized pattern detected in input.")

        fb_pattern = r"^https?:\/\/(?:[a-zA-Z0-9-]+\.)?(facebook\.com|fb\.watch|fb\.me|fb\.gg)\/.+$"
        if not re.match(fb_pattern, v, re.IGNORECASE):
            raise ValueError("Invalid URL. Only official Facebook, Reels, or Watch links are allowed.")
            
        return v

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

@app.post("/api/get_info")
async def get_video_info(data: VideoRequest):
    url = data.url
        
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
        parsed_url = urlparse(stream_url)
        allowed_domains = ["fbcdn.net", "facebook.com", "instagram.com"]
        
        if not any(parsed_url.netloc.endswith(domain) for domain in allowed_domains):
            raise HTTPException(status_code=403, detail="Access denied: Invalid stream source.")
            
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(stream_url, headers=headers, stream=True)
        
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

@app.get("/sitemap.xml")
async def get_sitemap():
    sitemap_path = os.path.join("public", "sitemap.xml")
    if os.path.exists(sitemap_path):
        with open(sitemap_path, "r", encoding="utf-8") as f:
            content = f.read()
        return FastAPIResponse(content=content, media_type="application/xml")
    return FastAPIResponse(content="<error>Sitemap not found</error>", status_code=404, media_type="application/xml")

if os.path.exists("public"):
    app.mount("/static", StaticFiles(directory="public"), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def read_index():
        return FileResponse("public/index.html")
