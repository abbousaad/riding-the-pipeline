"""Recorded, non-streaming LLM Gateway calls; stdlib only, no implicit retries."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.llmgateway.io/v1"
HEADERS = {"Content-Type": "application/json", "X-No-Fallback": "true",
           "X-No-Cache": "true"}


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def reject_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]").replace(
            json.dumps(secret)[1:-1], "[REDACTED]")
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {redact(key, secret): redact(item, secret) for key, item in value.items()}
    return value


class GatewayError(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a bearer token to another origin on a redirect.
        return None


def transport(request, timeout):
    return urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)


class Budget:
    """Request cap is hard; reported-cost guard can overshoot by one request."""

    def __init__(self, max_requests, max_reported_cost_usd):
        self.max_requests = max_requests
        self.max_cost = max_reported_cost_usd
        self.requests = 0
        self.reported_cost = 0.0
        self.unknown_cost_calls = 0

    def reserve(self):
        if self.requests >= self.max_requests:
            raise GatewayError("request_cap")
        if self.unknown_cost_calls:
            raise GatewayError("unknown_cost_stop")
        if self.reported_cost >= self.max_cost:
            raise GatewayError("reported_cost_cap")
        self.requests += 1

    def account(self, response):
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get("cost_details") or {}
        cost = details.get("total_cost") if isinstance(details, dict) else None
        if cost is None:
            cost = usage.get("cost")
        if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            self.unknown_cost_calls += 1
        else:
            self.reported_cost += cost

    def snapshot(self):
        return {"requests_attempted": self.requests,
                "reported_cost_usd": self.reported_cost,
                "unknown_cost_calls": self.unknown_cost_calls,
                "max_requests": self.max_requests,
                "max_reported_cost_usd": self.max_cost}


class Client:
    def __init__(self, api_key, model, directory, budget, *, timeout=90, send=transport):
        if not api_key or not api_key.strip():
            raise ValueError("LLM_GATEWAY_API_KEY is required for live mode")
        self.key = api_key
        self.model = model
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.budget = budget
        self.timeout = timeout
        self.send = send
        self.count = 0

    def complete(self, system, user):
        self.budget.reserve()
        self.count += 1
        payload = {**self.model["parameters"], "model": self.model["id"], "stream": False,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        record = {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "endpoint": BASE_URL + "/chat/completions", "request": payload,
                  "request_sha256": hashlib.sha256(encoded).hexdigest(),
                  "control_headers": HEADERS, "response": None,
                  "response_text": None, "error": None}
        start = time.monotonic()
        parsed = None
        try:
            request = urllib.request.Request(record["endpoint"], data=encoded,
                       headers={**HEADERS, "Authorization": "Bearer " + self.key})
            with self.send(request, self.timeout) as response:
                record["http_status"] = response.status
                record["cache_header"] = response.headers.get("x-llmgateway-cache", "")
                record["response_text"] = response.read().decode("utf-8")
            parsed = json.loads(record["response_text"], parse_constant=reject_constant,
                                parse_float=finite_float)
            record["response"] = parsed
            if not isinstance(parsed, dict):
                raise GatewayError("invalid_gateway_response")
            metadata = parsed.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise GatewayError("invalid_gateway_metadata")
            if metadata.get("cached") or record["cache_header"].upper() == "HIT":
                raise GatewayError("cached_response_rejected")
            requested_provider = self.model["id"].split("/", 1)[0]
            if metadata.get("used_provider") not in (None, requested_provider):
                raise GatewayError("unexpected_provider")
            choices = parsed["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise GatewayError("invalid_gateway_choices")
            choice = choices[0]
            if choice.get("finish_reason") == "length":
                raise GatewayError("truncated_response")
            if choice.get("finish_reason") == "content_filter":
                raise GatewayError("filtered_response")
            message = choice["message"]
            if message.get("refusal"):
                raise GatewayError("provider_refusal")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise GatewayError("empty_response")
            return content
        except urllib.error.HTTPError as exc:
            record["http_status"] = exc.code
            with exc:
                record["response_text"] = exc.read().decode("utf-8", errors="replace")
            record["error"] = "http_error"
            raise GatewayError("http_error") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            record["error"] = "transport_error"
            raise GatewayError("transport_error") from None
        except GatewayError as exc:
            record["error"] = exc.kind
            raise
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            record["error"] = "invalid_gateway_response"
            raise GatewayError("invalid_gateway_response") from None
        finally:
            self.budget.account(parsed)
            record["latency_seconds"] = time.monotonic() - start
            record["budget_after_call"] = self.budget.snapshot()
            # Also redact a key unexpectedly echoed inside a provider error body.
            save_json(self.directory / f"call-{self.count:04d}.json", redact(record, self.key))
