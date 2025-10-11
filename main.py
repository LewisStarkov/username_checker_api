import asyncio
import time
import httpx
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from bs4 import BeautifulSoup
import logging

FRAGMENT_URL = "https://fragment.com/username/"
THREADS = 10

app = FastAPI()
logger = logging.getLogger(__name__)


async def scrape_username_status(
    client: httpx.AsyncClient, username: str
) -> str | None:
    url = f"{FRAGMENT_URL}{username}"
    try:
        r = await client.get(url, timeout=20.0)
    except httpx.TimeoutException:
        return "timeout"
    except Exception as e:
        logger.error(f"Error fetching {username}: {e}")
        return "error"

    if r.status_code == 403:
        return "cf_blocked"

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        status_section = soup.find(class_="tm-section-header-status")
        if not status_section:
            return "EMPTY"

        status_class = status_section.get("class", [])
        mapping = {
            "tm-status-taken": "taken",
            "tm-status-avail": "for sale",
            "tm-status-unavail": "unavailable",
        }
        for key, value in mapping.items():
            if key in status_class:
                return value
        return "unknown"
    except Exception as e:
        logger.error(f"Error parsing response for {username}: {e}")
        return "parse_error"


async def worker(
    worker_id: int, queue: asyncio.Queue, results: dict, client: httpx.AsyncClient
):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        username = item
        start_ts = time.time()
        try:
            status = await scrape_username_status(client, username)
            elapsed = time.time() - start_ts
            results[username] = status
            print(f"[{worker_id}] {username} → {status} ({elapsed:.2f}s)", flush=True)
        except Exception as e:
            logger.error(f"[{worker_id}] Error processing {username}: {e}")
            results[username] = "error"
        finally:
            queue.task_done()


@app.get("/status")
async def get_status():
    return {"status": "ok", "message": "Fragment Checker API is running"}


@app.post("/check")
async def check_usernames(request: Request):
    """
    Parameters:
    - usernames: list of usernames to check

    Returns:
    - dictionary of usernames and their status
    """
    try:
        data = await request.json()
        usernames = data.get("usernames", [])

        if not usernames:
            raise HTTPException(status_code=400, detail="No usernames provided")

        if len(usernames) > 500:
            raise HTTPException(status_code=400, detail="Too many usernames (max 500)")

        queue = asyncio.Queue()
        results = {}

        for username in usernames:
            await queue.put(username.lower())

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(
            http2=True, headers=headers, follow_redirects=True
        ) as client:
            workers = [
                asyncio.create_task(worker(i, queue, results, client))
                for i in range(THREADS)
            ]
 
            await queue.join()

            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers)

        logger.info(f"Processed {len(usernames)} usernames, results: {len(results)}")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in check_usernames endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
