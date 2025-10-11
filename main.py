import asyncio
import time
import httpx
import uvicorn
from fastapi import FastAPI, Request
from bs4 import BeautifulSoup

FRAGMENT_URL = "https://fragment.com/username/"
THREADS = 10

app = FastAPI()


async def scrape_username_status(
    client: httpx.AsyncClient, username: str
) -> str | None:
    url = f"{FRAGMENT_URL}{username}"
    try:
        r = await client.get(url, timeout=20.0)
    except Exception:
        return "error"

    if r.status_code == 403:
        return "cf_blocked"

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
        status = await scrape_username_status(client, username)
        elapsed = time.time() - start_ts

        results[username] = status
        queue.task_done()

        print(f"[{worker_id}] {username} → {status} ({elapsed:.2f}s)", flush=True)


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
    Example:
    {
      "usernames": ["test1", "test2", "something"]
    }
    Returns:
    {
      "test1": "taken",
      "test2": "EMPTY",
      "something": "for sale"
    }
    """
    data = await request.json()
    usernames = data.get("usernames", [])

    if not usernames:
        return {"error": "No usernames provided"}

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

    return results


if __name__ == "__main__":

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)