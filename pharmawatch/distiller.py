"""
distiller.py — Clean raw SerpApi JSON responses into structured PharmaWatch records.

Extracts:
- platform (e.g., 1mg, PharmEasy, Netmeds, Apollo Pharmacy, Medplus)
- price_inr (float)
- medicine_name / title
- availability / delivery
- link
- raw_price_str
- thumbnail
"""

import re
from typing import Dict, List, Optional

# Domains and name patterns for recognized Indian pharma platforms
TARGET_PHARMA_DOMAINS = [
    "1mg.com",
    "pharmeasy.in",
    "netmeds.com",
    "apollopharmacy.in",
    "apollo247.com",
    "medplusbazaar.com",
]

TARGET_PHARMA_NAMES = [
    "1mg",
    "pharmeasy",
    "netmeds",
    "apollo",
    "apollo247",
    "medplus",
]


def parse_price_inr(price_str: Optional[str]) -> Optional[float]:
    """
    Extract clean numeric price in INR from messy string formats.
    Handles: "₹45.50", "Rs 45", "45.50", "MRP ₹1,250.00", "Rs. 120", etc.
    """
    if not price_str:
        return None

    # Remove commas used in numbers like "1,250"
    cleaned = str(price_str).replace(",", "")
    
    # Regex to capture integer or decimal numbers after currency markers or standalones
    match = re.search(r"(?:[₹]|Rs\.?|MRP\s*₹?|\$)?\s*(\d+(?:\.\d{1,2})?)", cleaned, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def identify_platform(source: str, link: str) -> Optional[str]:
    """
    Identify if a result belongs to a target Indian pharma platform.
    Returns normalized platform name or None if not matched.
    """
    combined = f"{source} {link}".lower()

    if "1mg" in combined:
        return "1mg"
    elif "pharmeasy" in combined:
        return "PharmEasy"
    elif "netmeds" in combined:
        return "Netmeds"
    elif "apollo" in combined:
        return "Apollo Pharmacy"
    elif "medplus" in combined:
        return "Medplus"
    
    return None


PLATFORM_DOMAIN_MAP = {
    "1mg": "1mg.com",
    "PharmEasy": "pharmeasy.in",
    "Netmeds": "netmeds.com",
    "Apollo Pharmacy": "apollopharmacy.in",
    "Medplus": "medplusbazaar.com",
}


import urllib.parse


def sanitize_link(url: str) -> str:
    """
    Sanitize and URL-encode direct links to ensure spaces (%20) and characters do not break URLs.
    """
    if not url:
        return ""
    return urllib.parse.quote(url.strip(), safe=":/%?=#&+-@._~")


DIRECT_STORE_SEARCH_TEMPLATES = {
    "1mg": "https://www.1mg.com/search/all?name={query}",
    "PharmEasy": "https://pharmeasy.in/search/all?name={query}",
    "Netmeds": "https://www.netmeds.com/catalogsearch/result/{query}/all",
    "Apollo Pharmacy": "https://www.apollopharmacy.in/search-medicines/{query}",
    "Medplus": "https://www.medplusbazaar.com/search/{query}",
}


def build_direct_store_link(platform: str, medicine_name: str, raw_link: str) -> str:

    """
    Construct direct merchant store link (1mg, PharmEasy, Netmeds, Apollo, Medplus)
    so clicking 'Visit Site' lands directly on the pharmacy store website rather than Google Shopping.
    """
    if raw_link and not "google.co.in/search" in raw_link and not "google.com/search" in raw_link:
        return sanitize_link(raw_link)

    query_encoded = urllib.parse.quote(medicine_name.strip())
    platform_key = (platform or "").strip()

    if platform_key in DIRECT_STORE_SEARCH_TEMPLATES:
        return DIRECT_STORE_SEARCH_TEMPLATES[platform_key].format(query=query_encoded)

    return sanitize_link(raw_link)


def distill_shopping_results(raw_json: dict, filter_known_platforms: bool = True) -> List[Dict]:
    """
    Distill raw google_shopping SerpApi response into clean, structured records.

    Args:
        raw_json: Raw dictionary returned by SerpApi search.
        filter_known_platforms: If True, only keep results matching known Indian pharma platforms.

    Returns:
        List of dicts: [
            {
                "platform": str,
                "platform_domain": str,
                "platform_logo": str,
                "price_inr": float,
                "medicine_name": str,
                "availability": str,
                "link": str,
                "google_shopping_link": str,
                "raw_price_str": str,
                "thumbnail": str,
            },
            ...
        ]
    """
    shopping_results = raw_json.get("shopping_results", [])
    distilled = []

    for item in shopping_results:
        source = item.get("source", "")
        raw_link = (
            item.get("link")
            or item.get("product_link")
            or item.get("merchant_link")
            or item.get("seller_link")
            or ""
        )
        google_shopping_link = sanitize_link(raw_link)

        platform = identify_platform(source, raw_link)
        if filter_known_platforms and not platform:
            continue

        raw_price = item.get("price")
        extracted_price = item.get("extracted_price")

        # Prefer extracted_price if available, otherwise parse price string
        if isinstance(extracted_price, (int, float)):
            price_inr = float(extracted_price)
        else:
            price_inr = parse_price_inr(raw_price)

        if price_inr is None:
            continue

        delivery = item.get("delivery", "Standard Delivery")
        title = item.get("title", "")
        thumbnail = item.get("thumbnail") or item.get("serpapi_thumbnail") or ""
        platform_logo = item.get("source_icon") or ""
        platform_name = platform or source or "Unknown"
        platform_domain = PLATFORM_DOMAIN_MAP.get(platform_name, "")
        direct_link = build_direct_store_link(platform_name, title, raw_link)

        distilled.append({
            "platform": platform_name,
            "platform_domain": platform_domain,
            "platform_logo": platform_logo,
            "price_inr": price_inr,
            "medicine_name": title,
            "availability": delivery,
            "link": direct_link,
            "direct_link": direct_link,
            "google_link": google_shopping_link,
            "google_shopping_link": google_shopping_link,
            "raw_price_str": str(raw_price) if raw_price else f"₹{price_inr}",
            "thumbnail": thumbnail,
        })


    return distilled




def distill_scholar_results(raw_json: dict, max_results: int = 3) -> List[Dict]:
    """
    Distill raw google_scholar SerpApi response for Phase 5 generic bioequivalence verification.

    Args:
        raw_json: Raw dictionary returned by SerpApi google_scholar search.
        max_results: Top N results to return.

    Returns:
        List of dicts: [
            {
                "title": str,
                "snippet": str,
                "link": str,
                "publication_info": str,
            },
            ...
        ]
    """
    organic_results = raw_json.get("organic_results", [])
    distilled = []

    for item in organic_results[:max_results]:
        publication_info = item.get("publication_info", {})
        summary = publication_info.get("summary", "") if isinstance(publication_info, dict) else str(publication_info)

        distilled.append({
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "link": item.get("link", ""),
            "publication_info": summary,
        })

    return distilled
