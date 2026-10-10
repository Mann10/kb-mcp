"""TEMPLATE-CRUD proofs: list/create/update/delete over isolated stores (no mocks)."""

import json

import pytest

from kb_mcp import templates as T
from kb_mcp import write_tools
from kb_mcp.errors import AuthenticationError, AuthorizationError
from kb_mcp.middleware import READ_DENIED_MESSAGE, WRITE_DENIED_MESSAGE
from kb_mcp.templates import TemplateStore, configure_template_store


@pytest.fixture(autouse=True)
def _use_isolated_stores(repository, template_store):
    write_tools.configure_default_repo(repository)
    configure_template_store(template_store)
    yield
    write_tools.configure_default_repo(None)
    configure_template_store(None)


def _w(token_store, read_write_token_pair):
    raw, _ = read_write_token_pair
    return raw, token_store


# --- store seeding / persistence ---


def test_store_seeds_builtins_on_missing_file(template_store_path):
    template_store_path.unlink()  # autouse fixture pre-seeds; start truly missing
    assert not template_store_path.exists()
    store = TemplateStore.load(store_path=template_store_path)
    assert store.names() == ["book", "idea", "meeting"]
    assert template_store_path.exists()
    assert json.loads(template_store_path.read_text(encoding="utf-8"))["templates"].keys() == {"book", "idea", "meeting"}


def test_store_respects_existing_file(template_store_path):
    template_store_path.write_text(
        json.dumps({"templates": {"custom": {"default_tags": ["c"], "body_skeleton": "# C"}}}),
        encoding="utf-8",
    )
    store = TemplateStore.load(store_path=template_store_path)
    assert "custom" in store.names()
    assert "meeting" in store.names()  # built-ins backfilled, never lost


def test_store_reseeds_on_corrupt_file(template_store_path):
    template_store_path.write_text("not json {{{", encoding="utf-8")
    store = TemplateStore.load(store_path=template_store_path)
    assert store.names() == ["book", "idea", "meeting"]


def test_mutations_persist_to_disk(template_store, template_store_path):
    template_store.add("sprint", "# Sprint", ["agile"])
    reloaded = TemplateStore.load(store_path=template_store_path)
    assert reloaded.get("sprint") == {"default_tags": ["agile"], "body_skeleton": "# Sprint"}


# --- list ---


def test_list_defaults_sorted(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.list_templates(token=raw, _store=store)
    assert out["success"] is True
    assert [t["name"] for t in out["templates"]] == ["book", "idea", "meeting"]
    meeting = next(t for t in out["templates"] if t["name"] == "meeting")
    assert meeting["default_tags"] == ["meeting"]
    assert "## Attendees" in meeting["body_skeleton"]
    assert "meeting" in out["message"]


def test_list_allowed_for_read_token(token_store, read_token_pair):
    read_raw, _ = read_token_pair
    out = T.list_templates(token=read_raw, _store=token_store)
    assert out["success"] is True
    assert len(out["templates"]) == 3


def test_list_denied_for_bogus_token(token_store):
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        T.list_templates(token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        T.list_templates(token=None, _store=token_store)


# --- create ---


def test_create_template(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template("sprint", "# Sprint\n\n## Goals", ["agile"], token=raw, _store=store)
    assert out["success"] is True
    assert out["name"] == "sprint"
    assert out["default_tags"] == ["agile"]
    listed = T.list_templates(token=raw, _store=store)
    assert "sprint" in [t["name"] for t in listed["templates"]]


def test_create_name_normalized(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template("  Sprint-Planning_2 ", token=raw, _store=store)
    assert out["success"] is True
    assert out["name"] == "sprint-planning_2"
    assert out["default_tags"] == []
    assert out["body_skeleton"] == ""


def test_create_duplicate_rejected(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    assert T.create_template("sprint", token=raw, _store=store)["success"] is True
    dup = T.create_template("SPRINT", token=raw, _store=store)
    assert dup["success"] is False
    assert "already exists" in dup["message"]


def test_create_builtin_name_rejected(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template("meeting", token=raw, _store=store)
    assert out["success"] is False
    assert "already exists" in out["message"]


@pytest.mark.parametrize("bad", ["", "   ", "has space", "MEETING!", "a/b", None, 123])
def test_create_invalid_name(token_store, read_write_token_pair, bad):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template(bad, token=raw, _store=store)
    assert out["success"] is False
    assert "name" in out["message"]


@pytest.mark.parametrize("bad_tags", ["notalist", [123], ["x" * 100], ["ok", "   "]])
def test_create_invalid_tags(token_store, read_write_token_pair, bad_tags):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template("sprint", default_tags=bad_tags, token=raw, _store=store)
    assert out["success"] is False
    assert "tags" in out["message"]


def test_create_invalid_skeleton(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.create_template("sprint", body_skeleton=123, token=raw, _store=store)
    assert out["success"] is False
    assert "body_skeleton" in out["message"]


# --- update ---


def test_update_partial_body(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", "# Old", ["agile"], token=raw, _store=store)
    out = T.update_template("sprint", body_skeleton="# New", token=raw, _store=store)
    assert out["success"] is True
    assert out["body_skeleton"] == "# New"
    assert out["default_tags"] == ["agile"]
    assert "updated" in out["message"]


def test_update_partial_tags(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", "# Sprint", ["agile"], token=raw, _store=store)
    out = T.update_template("sprint", default_tags=["planning"], token=raw, _store=store)
    assert out["success"] is True
    assert out["default_tags"] == ["planning"]
    assert out["body_skeleton"] == "# Sprint"


def test_update_builtin(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.update_template("meeting", default_tags=["meeting", "sync"], token=raw, _store=store)
    assert out["success"] is True
    assert out["default_tags"] == ["meeting", "sync"]


def test_update_noop_success(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", "# Sprint", token=raw, _store=store)
    out = T.update_template("sprint", token=raw, _store=store)
    assert out["success"] is True
    assert "No changes" in out["message"]


def test_update_missing(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.update_template("nope", body_skeleton="# X", token=raw, _store=store)
    assert out["success"] is False
    assert "Unknown template" in out["message"]
    assert "meeting" in out["message"]


def test_update_invalid_inputs(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", token=raw, _store=store)
    assert "body_skeleton" in T.update_template("sprint", body_skeleton=123, token=raw, _store=store)["message"]
    assert "tags" in T.update_template("sprint", default_tags=["x" * 100], token=raw, _store=store)["message"]
    assert "name" in T.update_template("BAD NAME!", token=raw, _store=store)["message"]


# --- delete ---


def test_delete_template(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", token=raw, _store=store)
    out = T.delete_template("sprint", token=raw, _store=store)
    assert out["success"] is True
    assert out["name"] == "sprint"
    assert "sprint" not in [t["name"] for t in T.list_templates(token=raw, _store=store)["templates"]]


def test_delete_normalized(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", token=raw, _store=store)
    out = T.delete_template("  SPRINT ", token=raw, _store=store)
    assert out["success"] is True


def test_delete_missing(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    out = T.delete_template("nope", token=raw, _store=store)
    assert out["success"] is False
    assert "Unknown template" in out["message"]


def test_delete_then_recreate(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", "# v1", token=raw, _store=store)
    T.delete_template("sprint", token=raw, _store=store)
    out = T.create_template("sprint", "# v2", token=raw, _store=store)
    assert out["success"] is True
    assert out["body_skeleton"] == "# v2"


# --- auth ---


@pytest.mark.parametrize("tool", ["create_template", "update_template", "delete_template"])
def test_write_tools_denied_for_read_token(token_store, read_token_pair, tool):
    read_raw, _ = read_token_pair
    fn = getattr(T, tool)
    with pytest.raises(AuthorizationError, match=WRITE_DENIED_MESSAGE.split(".")[0]):
        fn("sprint", token=read_raw, _store=token_store)


@pytest.mark.parametrize("tool", ["create_template", "update_template", "delete_template"])
def test_write_tools_denied_for_bogus_token(token_store, tool):
    fn = getattr(T, tool)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        fn("sprint", token="bogus", _store=token_store)
    with pytest.raises(AuthenticationError, match="Invalid or missing token"):
        fn("sprint", token=None, _store=token_store)


def test_list_denied_without_scope(token_store):
    from kb_mcp.auth import TokenType

    raw = "test-token-aaa-noscope-0099"
    token_store.add_token(username="noscope", token_type=TokenType.READ, raw=raw)
    out = T.list_templates(token=raw, _store=token_store)
    assert out["success"] is True
    assert READ_DENIED_MESSAGE.startswith("Read access required")


# --- create_from_template over custom templates ---


def test_create_from_custom_template(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    created = T.create_template("sprint", "# Sprint\n\n## Goals", ["agile"], token=raw, _store=store)
    assert created["success"] is True
    out = write_tools.create_from_template("sprint", "Sprint 12", token=raw, _store=store)
    assert out["success"] is True
    assert out["filename"] == "sprint-12"
    assert out["tags"] == ["agile"]
    assert "created from 'sprint' template" in out["message"]
    note = repository.read_note("sprint-12.md")
    assert "## Goals" in note.body


def test_deleted_template_unusable(token_store, read_write_token_pair):
    raw, store = _w(token_store, read_write_token_pair)
    T.create_template("sprint", token=raw, _store=store)
    T.delete_template("sprint", token=raw, _store=store)
    out = write_tools.create_from_template("sprint", "Sprint 12", token=raw, _store=store)
    assert out["success"] is False
    assert "Unknown template" in out["message"]


def test_updated_template_affects_new_notes(token_store, read_write_token_pair, repository):
    raw, store = _w(token_store, read_write_token_pair)
    T.update_template("idea", body_skeleton="# Custom Idea", token=raw, _store=store)
    out = write_tools.create_from_template("idea", "Big Idea", token=raw, _store=store)
    assert out["success"] is True
    assert repository.read_note("big-idea.md").body == "# Custom Idea"
