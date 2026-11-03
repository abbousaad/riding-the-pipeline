"""Lossless action parsing; authorization is a separate operation."""

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class Action:
    name: str
    arguments: dict


@dataclass(frozen=True)
class Response:
    raw: str
    explanation: str
    actions: tuple[Action, ...]
    error: str | None = None


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def parse_response(raw: str) -> Response:
    """Retain unknown actions and legacy arguments without inventing any calls.

    Legacy strings are accepted for historical analysis. Parameter suffixes are
    preserved under 'legacy_argument'; the executor will reject ambiguous shapes.
    Any malformed call invalidates the whole response before any action executes.
    """
    if not isinstance(raw, str):
        return Response(repr(raw), "", (), "response must be text")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0].lower() not in ("```", "```json") or lines[-1] != "```":
            return Response(raw, "", (), "invalid JSON fence")
        text = "\n".join(lines[1:-1])
    try:
        obj = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if not isinstance(obj, dict):
            raise ValueError("response must be an object")
        if "tool_calls" not in obj or not isinstance(obj["tool_calls"], list):
            raise ValueError("tool_calls must be an explicit list")
        explanation = obj.get("explanation", obj.get("reasoning", ""))
        if not isinstance(explanation, str):
            raise ValueError("explanation must be text")
        actions = []
        for call in obj["tool_calls"]:
            if isinstance(call, str):
                name, separator, suffix = call.partition(":")
                arguments = {"legacy_argument": suffix} if separator else {}
            elif isinstance(call, dict) and set(call) == {"name", "arguments"}:
                name, arguments = call["name"], call["arguments"]
                if not isinstance(arguments, dict):
                    raise ValueError("action arguments must be an object")
            else:
                raise ValueError("action must be a name or a {name, arguments} object")
            if not isinstance(name, str) or not name or name.strip() != name:
                raise ValueError("action name must be nonempty without surrounding whitespace")
            actions.append(Action(name, arguments))
        return Response(raw, explanation, tuple(actions))
    except (ValueError, TypeError) as exc:
        return Response(raw, "", (), str(exc))
