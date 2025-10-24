import asyncio
import httpx
import uvicorn
import logging
from fastapi import FastAPI, Request, HTTPException
from bs4 import BeautifulSoup

FRAGMENT_SEARCH_URL = "https://fragment.com/?query="
THREADS = 10

app = FastAPI()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


def parse_status_from_html(html: str, username: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    
    target_username = f"@{username}"
    rows = soup.select('tbody.tm-high-cells tr.tm-row-selectable')
    
    target_row = None
    for row in rows:
        value_el = row.select_one('.table-cell-value.tm-value')
        if value_el and value_el.get_text(strip=True) == target_username:
            target_row = row
            break
    
    if not target_row:
        return "not_found"
    
    if "js-auction-unavail" in target_row.get("class", []):
        return "unavailable"
    
    status_elements = target_row.select('[class*="tm-status-"]')
    for status_el in status_elements:
        text = status_el.get_text(strip=True).lower()
        
        if "available" in text:
            return "available"
        elif "for sale" in text:
            return "for_sale"
        elif text == "sold":
            return "sold"
        elif text == "taken":
            return "taken"
        elif "unavailable" in text:
            return "unavailable"
    
    timer = target_row.select_one('.tm-timer')
    if timer and "left" in timer.get_text().lower():
        return "on_auction"
    
    return "not_found"


async def scrape_username_status(client: httpx.AsyncClient, username: str) -> str:
    try:
        r = await client.get(f"{FRAGMENT_SEARCH_URL}{username}", timeout=20)
        if r.status_code in (403, 429):
            return "cf_blocked"
        return parse_status_from_html(r.text, username)
    except httpx.TimeoutException:
        return "timeout"
    except Exception:
        return "error"


async def process_usernames(usernames: list[str]) -> dict[str, str]:
    sem = asyncio.Semaphore(THREADS)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, http2=True) as client:

        async def bound_task(username: str):
            async with sem:
                status = await scrape_username_status(client, username)
                # logger.info(f"{username} - {status}")
                return username, status

        results = await asyncio.gather(*(bound_task(u) for u in usernames))

    return {username: status for username, status in results}


@app.get("/status")
async def get_status():
    """
    Health check endpoint to verify the API is running.
    
    Returns:
        dict: Status information containing:
            - status (str): Always "ok" if the service is running
            - message (str): Human-readable status message
    
    Example:
        GET /status
        
        Response:
        {
            "status": "ok",
            "message": "Fragment Checker API is running"
        }
    """
    return {"status": "ok", "message": "Fragment Checker API is running"}


@app.post("/check")
async def check_usernames(request: Request):
    """
    Check the status of multiple Telegram usernames on Fragment marketplace.
    
    This endpoint accepts a list of usernames and returns their current status
    on the Fragment platform (available, for sale, taken, unavailable, etc.).
    
    Args:
        request (Request): FastAPI request object containing JSON body with:
            - usernames (list[str]): List of Telegram usernames to check (without @)
    
    Returns:
        dict[str, str]: Dictionary mapping each username to its status:
            - "available": Username is available for sale or auction
            - "for_sale": Username is available for purchase at a fixed price
            - "on_auction": Username is currently being auctioned
            - "taken": Username is already claimed by someone
            - "sold": Username was recently sold
            - "unavailable": Username exists but is not available for sale
            - "not_found": Username was not found in search results
            - "cf_blocked": Request blocked by Cloudflare (403/429)
            - "timeout": Request timed out
            - "error": Other error occurred during processing
    
    Raises:
        HTTPException: 
            - 400: No usernames provided in request
            - 500: Internal server error during processing
    
    Example:
        POST /check
        Content-Type: application/json
        
        {
            "usernames": ["sadish", "lewis", "nonexistent"]
        }
        
        Response:
        {
            "sadish": "for_sale",
            "lewis": "sold",
            "nonexistent": "not_found"
        }
    
    Note:
        - Usernames are automatically converted to lowercase
        - Multiple usernames are processed concurrently (max 10 parallel requests)
        - Each request has a 20-second timeout
    """
    try:
        data = await request.json()
        usernames = data.get("usernames", [])
        if not usernames:
            raise HTTPException(status_code=400, detail="No usernames provided")
        return await process_usernames([u.lower() for u in usernames])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)