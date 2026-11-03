"""Native loopback Ollama recording with the frozen protocol-3 prompts."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error

from runtime import InfrastructureError, V2, decode

sys.path.insert(0, str(V2 / "local_ollama"))
import run_local as pilot


def now():
    return datetime.now(timezone.utc).isoformat()


def save_new(path, value):
    path = Path(path)
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def client_config(study):
    model = study["generator"]
    if model["endpoint"] != pilot.BASE + "/chat":
        raise ValueError("only the local Ollama endpoint is permitted")
    return {"model": model["model"], "expected_digest": model["digest"],
            "options": {k: model[k] for k in ("temperature", "seed", "num_ctx", "num_predict")},
            "think": model["think"], "timeout_seconds": model["timeout_seconds"]}


def preflight(study, send=pilot.transport):
    try:
        return pilot.preflight(client_config(study), send)
    except (pilot.LocalError, OSError, ValueError, KeyError, TypeError) as exc:
        raise InfrastructureError("preflight: " + str(exc)) from exc


def environment_identity(metadata):
    return {"model_digest": metadata["installed_model"]["digest"],
            "show": metadata["show"], "version": metadata["version"],
            "platform": metadata["platform"], "machine": metadata["machine"],
            "python": metadata["python"]}


class Client:
    def __init__(self, study, prompts, schema, directory, metadata, cap, send=pilot.transport):
        self.config = client_config(study)
        self.prompts, self.schema = prompts, schema
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=False)
        self.metadata, self.cap, self.send = metadata, cap, send
        self.count = 0
        self.records = []

    def check_environment(self):
        pilot.installed(self.config, self.send)
        if decode(self.send("version", None, 15)) != self.metadata["version"]:
            raise InfrastructureError("ollama_version_changed")

    def complete(self, phase, view):
        if self.count >= self.cap:
            raise InfrastructureError("request_cap")
        self.count += 1
        payload = {"model": self.config["model"], "stream": False,
            "messages": [{"role": "system", "content": self.prompts[phase]},
                         {"role": "user", "content": json.dumps(view, sort_keys=True)}],
            "options": self.config["options"], "think": self.config["think"],
            "format": self.schema, "keep_alive": "5m"}
        record = {"created_utc": now(), "phase": phase, "request": payload,
            "endpoint": pilot.BASE + "/chat", "expected_digest": self.config["expected_digest"],
            "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "response_text": None, "response": None, "error": None, "chat_sent": False}
        start = time.monotonic()
        try:
            self.check_environment()
            record["chat_sent"] = True
            raw = self.send("chat", payload, self.config["timeout_seconds"])
            record["response_text"] = raw
            response = decode(raw)
            record["response"] = response
            if not isinstance(response, dict) or response.get("error"):
                raise InfrastructureError("invalid_server_response")
            if response.get("model") != self.config["model"]:
                raise InfrastructureError("unexpected_model")
            if response.get("done") is not True or response.get("done_reason") != "stop":
                raise InfrastructureError("unfinished_or_truncated_response")
            prompt_count, generated = response.get("prompt_eval_count"), response.get("eval_count")
            if type(prompt_count) is not int or type(generated) is not int or min(prompt_count, generated) < 0:
                raise InfrastructureError("token_counts_missing")
            if prompt_count + self.config["options"]["num_predict"] >= self.config["options"]["num_ctx"]:
                raise InfrastructureError("context_capacity_risk")
            if response["message"].get("tool_calls"):
                raise InfrastructureError("unexpected_native_tool_calls")
            content = response["message"].get("content")
            if not isinstance(content, str):
                raise InfrastructureError("content_missing")
            self.check_environment()
            return content
        except urllib.error.HTTPError as exc:
            with exc:
                record["http_status"] = exc.code
                record["response_text"] = exc.read().decode("utf-8", errors="replace")
            record["error"] = "http_error"
            raise InfrastructureError("http_error") from None
        except (OSError, urllib.error.URLError) as exc:
            record["error"] = "transport_error"
            raise InfrastructureError("transport_error") from exc
        except (pilot.LocalError, InfrastructureError) as exc:
            record["error"] = str(exc)
            raise InfrastructureError(str(exc)) from exc
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            record["error"] = "invalid_server_response"
            raise InfrastructureError("invalid_server_response") from exc
        finally:
            record["latency_seconds"] = time.monotonic() - start
            save_new(self.directory / f"call-{self.count:04d}.json", record)
            self.records.append(record)

    def usage(self):
        def count(record, key):
            response = record.get("response")
            value = response.get(key) if isinstance(response, dict) else None
            return value if type(value) is int and value >= 0 else 0
        return {"requests_attempted": self.count,
                "chat_requests_sent": sum(r["chat_sent"] for r in self.records),
                "latency_seconds": sum(r["latency_seconds"] for r in self.records),
                "prompt_tokens": sum(count(r, "prompt_eval_count") for r in self.records),
                "generated_tokens": sum(count(r, "eval_count") for r in self.records)}
