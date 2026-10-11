"""Supabase-backed template registry (V2-02).

Same API and semantics as :class:`TemplateStore` (filesystem): lowercase
``[a-z0-9_-]`` names, ``KeyError`` on duplicates/missing, built-ins always
present (seeded with ``ON CONFLICT DO NOTHING`` on first use, mirroring the
file store's reseed-on-missing behavior).

Connections are per-operation via :mod:`kb_mcp.db` (no pooling by design).
"""

import logging

from .db import connect
from .templates import BUILTIN_TEMPLATES

logger = logging.getLogger(__name__)


class SupabaseTemplateStore:
    """Template registry over Supabase Postgres; built-ins always present."""

    @classmethod
    def load(cls) -> "SupabaseTemplateStore":
        """Return a store bound to SUPABASE_DB_URL, seeding built-ins."""
        store = cls()
        store._seed_builtins()
        return store

    def _seed_builtins(self) -> None:
        with connect() as conn, conn.cursor() as cur:
            for name, spec in BUILTIN_TEMPLATES.items():
                cur.execute(
                    "INSERT INTO templates (name, body_skeleton, default_tags) "
                    "VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING",
                    (name, spec["body_skeleton"], list(spec["default_tags"])),
                )

    def __len__(self) -> int:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM templates")
            return cur.fetchone()[0]

    def names(self) -> list[str]:
        """Sorted template names for deterministic output."""
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM templates")
            return sorted(row[0] for row in cur.fetchall())

    def get(self, name: str) -> dict | None:
        """Return the spec for a normalized name, or None."""
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT body_skeleton, default_tags FROM templates WHERE name = %s",
                (name,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        body_skeleton, default_tags = row
        return {"default_tags": list(default_tags), "body_skeleton": body_skeleton}

    def add(
        self,
        name: str,
        body_skeleton: str = "",
        default_tags: list[str] | None = None,
    ) -> str:
        """Add a template; raises KeyError when the name already exists."""
        if self.get(name) is not None:
            raise KeyError(f"Template '{name}' already exists.")
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO templates (name, body_skeleton, default_tags) "
                    "VALUES (%s, %s, %s)",
                    (name, body_skeleton, list(default_tags or [])),
                )
        except Exception as e:
            from psycopg import errors as _pg_errors

            if isinstance(e, _pg_errors.UniqueViolation):
                raise KeyError(f"Template '{name}' already exists.") from e
            raise
        return name

    def update(
        self,
        name: str,
        body_skeleton: str | None = None,
        default_tags: list[str] | None = None,
    ) -> str:
        """Partially update a template; raises KeyError when missing."""
        with connect() as conn, conn.cursor() as cur:
            parts: list[str] = []
            params: list = []
            if body_skeleton is not None:
                parts.append("body_skeleton = %s")
                params.append(body_skeleton)
            if default_tags is not None:
                parts.append("default_tags = %s")
                params.append(list(default_tags))
            if parts:
                params.append(name)
                cur.execute(
                    f"UPDATE templates SET {', '.join(parts)} WHERE name = %s",  # noqa: S608
                    params,
                )
                if cur.rowcount == 0:
                    raise KeyError(f"Unknown template '{name}'.")
            elif self.get(name) is None:
                raise KeyError(f"Unknown template '{name}'.")
        return name

    def remove(self, name: str) -> str:
        """Delete a template; raises KeyError when missing."""
        with connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM templates WHERE name = %s", (name,))
            if cur.rowcount == 0:
                raise KeyError(f"Unknown template '{name}'.")
        return name


__all__ = ["SupabaseTemplateStore"]
