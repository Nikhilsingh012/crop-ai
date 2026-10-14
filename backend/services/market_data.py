"""Validated client and normalizers for the official data.gov.in mandi feed."""
import json
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import md5
import requests
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
DEFAULT_BASE_URL = "https://api.data.gov.in/resource"
SOURCE_URL = "https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"
PAGE_SIZE = 1000
PRICE_UNIT = "INR/quintal"


class MarketDataError(Exception):
    """A safe, user-displayable market data provider error."""


def _provider_config():
    base_url = os.getenv("DATA_GOV_IN_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    resource_id = os.getenv("DATA_GOV_IN_MANDI_RESOURCE_ID", DEFAULT_RESOURCE_ID).strip()
    if not base_url or not resource_id:
        raise MarketDataError("Configure DATA_GOV_IN_BASE_URL and DATA_GOV_IN_MANDI_RESOURCE_ID")
    return base_url, resource_id


def _decimal(value, field):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise MarketDataError(f"Invalid {field} in provider response")
    if not number.is_finite() or number <= 0:
        raise MarketDataError(f"Invalid {field} in provider response")
    return number.quantize(Decimal("0.01"))


def normalize_record(record, fetched_at=None):
    required = ("state", "district", "market", "commodity", "arrival_date")
    if not isinstance(record, dict) or any(not str(record.get(k, "")).strip() for k in required):
        raise MarketDataError("Provider record is missing required fields")
    unit = record.get("price_unit") or record.get("unit")
    if unit and str(unit).strip().casefold() not in {"inr/quintal", "rs/quintal", "rupees per quintal", "rupees/quintal"}:
        raise MarketDataError("Provider record uses a price unit that cannot be compared")
    raw_date = str(record["arrival_date"]).strip()
    parsed = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(raw_date, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise MarketDataError("Provider record has an invalid arrival date")
    if parsed > date.today():
        raise MarketDataError("Provider record has a future arrival date")
    minimum = _decimal(record.get("min_price"), "minimum price")
    modal = _decimal(record.get("modal_price"), "modal price")
    maximum = _decimal(record.get("max_price"), "maximum price")
    present = [p for p in (minimum, modal, maximum) if p is not None]
    if not present or (minimum is not None and modal is not None and minimum > modal) or (modal is not None and maximum is not None and modal > maximum) or (minimum is not None and maximum is not None and minimum > maximum):
        raise MarketDataError("Provider record has inconsistent price values")
    now = fetched_at or datetime.now(timezone.utc)
    dimensions = ["data.gov.in/AGMARKNET", str(record["commodity"]).strip(), str(record.get("variety") or "").strip(), str(record.get("grade") or "").strip(), str(record["state"]).strip(), str(record["district"]).strip(), str(record["market"]).strip(), parsed.isoformat(), PRICE_UNIT]
    source_record_key = md5("|".join(value.casefold() for value in dimensions).encode("utf-8")).hexdigest()
    return {
        "provider": "data.gov.in/AGMARKNET", "commodity": str(record["commodity"]).strip(),
        "source_record_key": source_record_key,
        "variety": (str(record.get("variety") or "").strip() or None),
        "grade": (str(record.get("grade") or "").strip() or None),
        "state": str(record["state"]).strip(), "district": str(record["district"]).strip(),
        "mandi": str(record["market"]).strip(), "observed_on": parsed,
        "minimum_price": minimum, "modal_price": modal, "maximum_price": maximum,
        "arrival_quantity": None, "arrival_unit": None, "price_unit": PRICE_UNIT,
        "source_url": SOURCE_URL, "source_updated_at": None, "fetched_at": now,
        "freshness": "fresh" if (now.date() - parsed).days <= 2 else "stale",
        "raw_metadata": record,
    }


def _request_page(api_key, offset, limit, filters=None, opener=None, base_url=None, resource_id=None):
    params = {"api-key": api_key, "format": "json", "offset": offset, "limit": limit}
    for key, value in (filters or {}).items():
        if value:
            params[f"filters[{key}]"] = value
    base_url, resource_id = (base_url, resource_id) if base_url and resource_id else _provider_config()
    url = f"{base_url}/{resource_id}"
    for attempt in range(3):
        try:
            if opener is not None:
                request_url = url + "?" + urlencode(params)
                req = Request(request_url, headers={"Accept": "application/json", "User-Agent": "CropAI-Mandi/1.0"})
                with opener(req, timeout=15) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            else:
                response = requests.get(url, params=params, headers={"Accept": "application/json", "User-Agent": "CropAI-Mandi/1.0"}, timeout=(5, 15))
                if response.status_code in (401, 403):
                    raise MarketDataError("data.gov.in rejected the configured API credentials")
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise MarketDataError("data.gov.in returned an unexpected response")
            return payload
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                if exc.code in (401, 403):
                    raise MarketDataError("data.gov.in rejected the configured API credentials")
                raise MarketDataError(f"data.gov.in request failed (HTTP {exc.code})")
        except (requests.Timeout, TimeoutError) as exc:
            if attempt == 2:
                raise MarketDataError("data.gov.in request timed out; check outbound HTTPS access from the backend host") from None
        except (requests.ConnectionError, URLError) as exc:
            if attempt == 2:
                raise MarketDataError("Could not connect to data.gov.in; check DNS, proxy, firewall, and outbound HTTPS access") from None
        except requests.RequestException as exc:
            if attempt == 2:
                raise MarketDataError("data.gov.in request failed; inspect the HTTP status and backend network configuration") from None
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            if attempt == 2:
                raise MarketDataError("data.gov.in returned an invalid JSON response") from None
        if attempt < 2:
            time.sleep(0.25 * (2 ** attempt))


def fetch_records(api_key=None, filters=None, max_records=10000, opener=urlopen):
    key = api_key or os.getenv("DATA_GOV_IN_API_KEY", "").strip()
    if not key:
        raise MarketDataError("Configure DATA_GOV_IN_API_KEY on the backend to fetch official mandi data")
    if max_records < 1 or max_records > 100000:
        raise ValueError("max_records must be between 1 and 100000")
    records, offset, total = [], 0, None
    base_url, resource_id = _provider_config()
    fetched_at = datetime.now(timezone.utc)
    while offset < max_records and (total is None or offset < total):
        limit = min(PAGE_SIZE, max_records - offset)
        payload = _request_page(key, offset, limit, filters, None if opener is urlopen else opener, base_url, resource_id)
        try:
            total = int(payload.get("total", offset + len(payload["records"])))
        except (ValueError, TypeError):
            raise MarketDataError("data.gov.in returned an invalid total count")
        page = payload["records"]
        if not page:
            break
        records.extend(normalize_record(item, fetched_at) for item in page)
        offset += len(page)
        if len(page) < limit:
            break
    return records
