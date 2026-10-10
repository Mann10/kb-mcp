"""Note-template registry with CRUD tools (TEMPLATE-CRUD).

Lineage: Phase 8 shipped ``create_from_template`` over a hardcoded in-code
``TEMPLATES`` dict (meeting/book/idea). This module promotes that dict to a
persistent registry so assistants can manage templates over MCP:

- ``BUILTIN_TEMPLATES`` — the 3 Phase 8 skeletons; seed for a fresh store.
- ``TemplateStore`` — JSON-backed registry mirroring ``TokenStore``
  conventions: ``KB_TEMPLATES_FILE`` env override, default
  ``~/knowledge-base/templates.json``, atomic temp-file + rename saves.
  Missing files seed built-ins; corrupt files warn + reseed (templates must
  always resolve — ``create_from_template`` depends on it).
- Gated tools — ``list_templates`` (read) + ``create/update/delete_template``
  (write), same ``token``/``_store`` + module-level ``configure_template_store``
  pattern as ``configure_default_repo``. ``create_from_template`` resolves
  through ``get_template_store()`` so custom templates work immediately.

Name rules: normalized ``strip().lower()``, must match ``^[a-z0-9_-]+$``.
Tag/skeleton validation mirrors ``write_tools`` messages.
"""

import json
import logging
import os
import re
from pathlib import Path

from .middleware import require_read, require_write

logger = logging.getLogger(__name__)

BUILTIN_TEMPLATES = {
    "meeting": {
        "default_tags": ["meeting"],
        "body_skeleton": "# Meeting Notes\n\n## Attendees\n\n- \n\n## Agenda\n\n- \n\n## Notes\n\n\n## Action Items\n\n- [ ] \n",
    },
    "book": {
        "default_tags": ["book"],
        "body_skeleton": "# Book Notes\n\n## Summary\n\n\n## Key Takeaways\n\n- \n\n## Quotes\n\n> \n\n## Rating\n\n_Notes: /5_\n",
    },
    "idea": {
        "default_tags": ["idea"],
        "body_skeleton": "# Idea\n\n## Idea\n\n\n## Why\n\n\n## Next Steps\n\n- [ ] \n",
    },
}

_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


def normalize_name(name: str | None) -> str | None:
    """Normalize a template name, or None when it is not a usable string."""
    if not isinstance(name, str):
        return None
    norm = name.strip().lower()
    if not norm or not _NAME_RE.match(norm):
        return None
    return norm


def _validate_tags(tags) -> str | None:
    """Return an error message for bad tag input, or None when valid."""
    if (
        not isinstance(tags, list)
        or any(not isinstance(t, str) for t in tags)
        or any(len(t) >= 100 for t in tags)
        or any(not t.strip() for t in tags)
    ):
        return "Invalid tags: must be a list of strings each under 100 characters."
    return None


class TemplateStore:
    """JSON-backed template registry; built-ins always present."""

    def __init__(self, store_path: Path | None = None):
        if store_path is None:
            env_path = os.environ.get("KB_TEMPLATES_FILE")
            if env_path:
                store_path = Path(env_path)
            else:
                store_path = Path.home() / "knowledge-base" / "templates.json"
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._templates: dict[str, dict] = {}

    def __len__(self) -> int:
        return len(self._templates)

    def save(self) -> None:
        """Atomically persist the registry (temp-file + rename)."""
        content = json.dumps({"templates": self._templates}, indent=2)
        temp_path = self.store_path.with_suffix(".tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            os.replace(temp_path, self.store_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    @classmethod
    def load(cls, store_path: Path | None = None) -> "TemplateStore":
        """Load a store from disk; missing/corrupt files reseed built-ins."""
        store = cls(store_path=store_path)
        try:
            text = store.store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("Template store %s missing; seeding built-ins", store.store_path)
            store._templates = {k: dict(v, default_tags=list(v["default_tags"])) for k, v in BUILTIN_TEMPLATES.items()}
            store.save()
            return store
        try:
            data = json.loads(text)
            raw = data["templates"]
            if not isinstance(raw, dict):
                raise ValueError("templates must be an object")
        except Exception as e:
            logger.warning("Template store %s corrupt (%s); reseeding built-ins", store.store_path, e)
            store._templates = {k: dict(v, default_tags=list(v["default_tags"])) for k, v in BUILTIN_TEMPLATES.items()}
            store.save()
            return store
        store._templates = {
            name: {"default_tags": list(spec.get("default_tags", [])), "body_skeleton": spec.get("body_skeleton", "")}
            for name, spec in raw.items()
            if isinstance(name, str) and isinstance(spec, dict)
        }
        for name, spec in BUILTIN_TEMPLATES.items():
            store._templates.setdefault(
                name, {"default_tags": list(spec["default_tags"]), "body_skeleton": spec["body_skeleton"]}
            )
        return store

    def names(self) -> list[str]:
        """Sorted template names for deterministic output."""
        return sorted(self._templates)

    def get(self, name: str) -> dict | None:
        """Return the spec for a normalized name, or None."""
        return self._templates.get(name)

    def add(self, name: str, body_skeleton: str = "", default_tags: list[str] | None = None) -> str:
        """Add a template; raises KeyError when the name already exists."""
        if name in self._templates:
            raise KeyError(f"Template '{name}' already exists.")
        self._templates[name] = {
            "default_tags": list(default_tags or []),
            "body_skeleton": body_skeleton,
        }
        self.save()
        return name

    def update(
        self,
        name: str,
        body_skeleton: str | None = None,
        default_tags: list[str] | None = None,
    ) -> str:
        """Partially update a template; raises KeyError when missing."""
        if name not in self._templates:
            raise KeyError(f"Unknown template '{name}'.")
        if body_skeleton is not None:
            self._templates[name]["body_skeleton"] = body_skeleton
        if default_tags is not None:
            self._templates[name]["default_tags"] = list(default_tags)
        self.save()
        return name

    def remove(self, name: str) -> str:
        """Delete a template; raises KeyError when missing."""
        if name not in self._templates:
            raise KeyError(f"Unknown template '{name}'.")
        del self._templates[name]
        self.save()
        return name


_configured_store: TemplateStore | None = None


def configure_template_store(store: TemplateStore | None) -> None:
    """Set the module-level template store (test injection point)."""
    global _configured_store
    _configured_store = store


def get_template_store() -> TemplateStore:
    """Return the injected store, or a fresh ``TemplateStore.load()``."""
    if _configured_store is not None:
        return _configured_store
    return TemplateStore.load()


def _unknown_message(name) -> str:
    valid = ", ".join(get_template_store().names())
    return f"Unknown template '{name}'. Valid templates: {valid}."


@require_read
def list_templates(*, token=None, _store=None) -> dict:
    """List all templates with skeletons and default tags (name-sorted)."""
    tstore = get_template_store()
    entries = [
        {
            "name": name,
            "default_tags": list(tstore.get(name)["default_tags"]),
            "body_skeleton": tstore.get(name)["body_skeleton"],
        }
        for name in tstore.names()
    ]
    return {
        "success": True,
        "templates": entries,
        "message": f"{len(entries)} template(s): {', '.join(tstore.names())}.",
    }


@require_write
def create_template(
    name: str,
    body_skeleton: str = "",
    default_tags: list[str] | None = None,
    *,
    token=None,
    _store=None,
) -> dict:
    """Create a template; reject duplicates with a structured exists-error."""
    norm = normalize_name(name)
    if norm is None:
        return {"success": False, "message": f"Invalid name '{name}': use letters, numbers, '-' or '_'."}
    if not isinstance(body_skeleton, str):
        return {"success": False, "message": "Invalid body_skeleton: must be a string."}
    tags = list(default_tags) if default_tags is not None else []
    tag_error = _validate_tags(tags)
    if tag_error:
        return {"success": False, "message": tag_error}
    tstore = get_template_store()
    try:
        tstore.add(norm, body_skeleton, tags)
    except KeyError:
        return {"success": False, "message": f"Template '{norm}' already exists."}
    return {
        "success": True,
        "name": norm,
        "default_tags": tags,
        "body_skeleton": body_skeleton,
        "message": f"Template '{norm}' created.",
    }


@require_write
def update_template(
    name: str,
    body_skeleton: str | None = None,
    default_tags: list[str] | None = None,
    *,
    token=None,
    _store=None,
) -> dict:
    """Partially update a template; no-op update is success (no-changes)."""
    norm = normalize_name(name)
    if norm is None:
        return {"success": False, "message": f"Invalid name '{name}': use letters, numbers, '-' or '_'."}
    if body_skeleton is not None and not isinstance(body_skeleton, str):
        return {"success": False, "message": "Invalid body_skeleton: must be a string."}
    tags = list(default_tags) if default_tags is not None else None
    if tags is not None:
        tag_error = _validate_tags(tags)
        if tag_error:
            return {"success": False, "message": tag_error}
    tstore = get_template_store()
    if tstore.get(norm) is None:
        return {"success": False, "message": _unknown_message(name)}
    if body_skeleton is None and tags is None:
        spec = tstore.get(norm)
        return {
            "success": True,
            "name": norm,
            "default_tags": list(spec["default_tags"]),
            "body_skeleton": spec["body_skeleton"],
            "message": f"No changes to template '{norm}'.",
        }
    tstore.update(norm, body_skeleton, tags)
    spec = tstore.get(norm)
    return {
        "success": True,
        "name": norm,
        "default_tags": list(spec["default_tags"]),
        "body_skeleton": spec["body_skeleton"],
        "message": f"Template '{norm}' updated.",
    }


@require_write
def delete_template(name: str, *, token=None, _store=None) -> dict:
    """Delete a template by name; missing is a structured unknown-error."""
    norm = normalize_name(name)
    if norm is None:
        return {"success": False, "message": f"Invalid name '{name}': use letters, numbers, '-' or '_'."}
    tstore = get_template_store()
    if tstore.get(norm) is None:
        return {"success": False, "message": _unknown_message(name)}
    tstore.remove(norm)
    return {"success": True, "name": norm, "message": f"Template '{norm}' deleted."}
