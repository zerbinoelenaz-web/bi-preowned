#!/usr/bin/env python3
"""Crawl AutoScout24.ch listings for a fixed set of sellers.

Python 3, standard library only. POSTs paginated search requests to the
AutoScout24.ch listings API, collects every listing for the configured
sellers and writes them to data/stock.json.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.autoscout24.ch/v1/listings/search?language=en"
SELLER_IDS = [60699, 105, 60812, 2304422]
PAGE_SIZE = 20
SLEEP_SECONDS = 4
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Directory layout: this file lives in <root>/crawler/, output goes to <root>/data/.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "stock.json")


def post_search(page):
    """POST one page of the search. Returns the decoded JSON response.

    Retries up to MAX_RETRIES times with increasing backoff on failure.
    """
    body = json.dumps({
        "query": {"sellerIds": SELLER_IDS},
        "pagination": {"page": page, "size": PAGE_SIZE},
        "sort": [{"type": "PRICE", "order": "ASC"}],
    }).encode("utf-8")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        request = urllib.request.Request(
            API_URL,
            data=body,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as exc:
            last_error = exc
            print("Request for page %d failed (attempt %d/%d): %s"
                  % (page, attempt, MAX_RETRIES, exc), file=sys.stderr)
            if attempt < MAX_RETRIES:
                backoff = SLEEP_SECONDS * attempt
                print("  retrying in %d seconds..." % backoff, file=sys.stderr)
                time.sleep(backoff)

    raise RuntimeError("Page %d failed after %d attempts: %s"
                       % (page, MAX_RETRIES, last_error))


def map_listing(listing):
    """Extract the fields we keep for one listing."""
    listing_id = listing["id"]
    make = listing["make"]
    model = listing["model"]
    seller = listing["seller"]
    images = listing["images"]

    return {
        "id": listing_id,
         "make": make["name"] if make else None,
        "model": model["name"] if model else None,
        "versionFullName": listing["versionFullName"],
        "firstRegistrationYear": listing["firstRegistrationYear"],
        "mileage": listing["mileage"],
        "price": listing["price"],
        "horsePower": listing["horsePower"],
        "transmissionType": listing["transmissionType"],
        "conditionType": listing["conditionType"],
        "createdDate": listing["createdDate"],
         "seller": {
            "id": seller["id"] if seller else None,
            "name": seller["name"] if seller else None,
            "city": seller["city"] if seller else None,
            "zipCode": seller["zipCode"] if seller else None,
        },
        "imageKey": images[0]["key"] if images else None,
        "listingUrl": "https://www.autoscout24.ch/de/d/%s" % listing_id,
    }


def crawl():
    """Page through the API and return the list of mapped listings."""
    all_listings = []
    page = 0

    while True:
        if page > 0:
            time.sleep(SLEEP_SECONDS)

        print("Fetching page %d..." % page, file=sys.stderr)
        response = post_search(page)

        batch = response["content"]
        total = response["totalElements"]
        all_listings.extend(map_listing(item) for item in batch)

        page += 1
        if page * PAGE_SIZE >= total:
            break

    return all_listings


def summarize(listings):
    """Print per-seller totals and the grand total."""
    per_seller = {}
    for item in listings:
        seller = item["seller"]
        key = (seller["id"], seller["name"])
        per_seller[key] = per_seller.get(key, 0) + 1

    print("\nListings per seller:")
    for (sid, name), count in sorted(per_seller.items(), key=lambda kv: kv[0][0]):
        print("  seller %s (%s): %d" % (sid, name, count))
    print("Grand total: %d" % len(listings))


def main():
    listings = crawl()

    if not listings:
        print("ERROR: zero listings returned; not writing %s" % OUTPUT_FILE,
              file=sys.stderr)
        sys.exit(1)

    summarize(listings)

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(listings),
        "listings": listings,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)
    print("\nWrote %d listings to %s" % (len(listings), OUTPUT_FILE))


if __name__ == "__main__":
    main()
