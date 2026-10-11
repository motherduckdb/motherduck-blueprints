"""A stateful stand-in for MotherDuck's SQL surface that replaces the duckdb module.

scripts/mock-test.sh and the end-to-end tests put this directory first on PYTHONPATH, so
`import duckdb` inside md-blueprints, and inside the fake `motherduck` CLI next to this file,
loads this module instead of the real client. It never opens a network connection.

The account lives in $MOCK_DUCKDB_STATE_DIR/state.json; tests seed it to describe existing
resources. Every statement is appended to queries.log (one line per statement for grep) and
queries.jsonl (exact text) in the same directory. Unknown statements raise RuntimeError so a
new query shape fails loudly instead of silently succeeding.

Environment switches kept for scripts/mock-test.sh:
  MOCK_SHARE_MISSING=true       no share exists (unless state.json lists shares explicitly)
  MOCK_DUPLICATE_FLIGHTS=true   two Flights share the wikipedia preview name
  MOCK_DUPLICATE_DIVES=true     two Dives share the wikipedia preview title
  MOCK_FLIGHT_RUN_STATUS=...    status reported for submitted Flight runs
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class Error(Exception):
    """Mirrors duckdb.Error so deploy error paths can be exercised."""


DEFAULT_USER = "ci@example.test"
SHARE_URL = "md:_share/mock/00000000-0000-0000-0000-000000000003"
STRING = r"'((?:[^']|'')*)'"
IDENT = r'"((?:[^"]|"")*)"'


class MockResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def _string(query: str, prefix: str) -> str:
    match = re.search(prefix + STRING, query)
    if not match:
        raise Error(f"Missing argument {prefix!r} in {query}")
    return match.group(1).replace("''", "'")


def _optional_string(query: str, prefix: str) -> str | None:
    match = re.search(prefix + STRING, query)
    return match.group(1).replace("''", "'") if match else None


def _ident(query: str, prefix: str) -> str:
    match = re.search(prefix + IDENT, query)
    if not match:
        raise Error(f"Missing identifier {prefix!r} in {query}")
    return match.group(1).replace('""', '"')


def _page(query: str, rows: list[tuple[Any, ...]]) -> MockResult:
    # MD_LIST_* functions return one page; callers must follow "offset" to read the rest.
    limit = re.search(r'"limit" := (\d+)', query)
    offset = re.search(r'"offset" := (\d+)', query)
    start = int(offset.group(1)) if offset else 0
    return MockResult(rows[start:start + int(limit.group(1))] if limit else rows[start:])


def _select_columns(query: str) -> list[str]:
    select = re.search(r"SELECT (.*?) FROM ", query, flags=re.DOTALL)
    return [column.strip() for column in select.group(1).split(",")] if select else []


def _read_text_argument(query: str) -> str:
    path = _optional_string(query, r"read_text\(")
    return Path(path).read_text(encoding="utf-8") if path else ""


def _references_literal(query: str, prefix: str) -> str:
    match = re.search(prefix + r"(\[.*?\])(?:;|, \"|\))", query, flags=re.DOTALL)
    return match.group(1) if match else "[]"


def _references_json(literal: str) -> str:
    # Equal SQL literals compare equal after md-blueprints normalizes the JSON.
    return "[]" if literal == "[]" else json.dumps([{"type": "fake", "url": literal}])


class MockConnection:
    def __init__(self, config: dict[str, Any] | None) -> None:
        token = (config or {}).get("motherduck_token")
        if not token:
            raise RuntimeError("motherduck_token is required by fake duckdb")
        self.state_dir = Path(os.environ["MOCK_DUCKDB_STATE_DIR"])
        self.state_path = self.state_dir / "state.json"

    # -- state ---------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        state: dict[str, Any] = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        for key in ("flights", "dives", "guides", "roles", "share_grantees", "share_patterns", "runs"):
            state.setdefault(key, {})
        state.setdefault("databases", [])
        state.setdefault("sequence", 0)
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def _new_id(state: dict[str, Any], base: int) -> str:
        state["sequence"] += 1
        return f"00000000-0000-0000-0000-{base + state['sequence']:012d}"

    @staticmethod
    def _user(state: dict[str, Any]) -> str:
        return str(state.get("current_user", DEFAULT_USER))

    def _log(self, query: str) -> None:
        with (self.state_dir / "queries.log").open("a", encoding="utf-8") as handle:
            handle.write(query + "\n")
        with (self.state_dir / "queries.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(query) + "\n")

    # -- statements ----------------------------------------------------------

    def execute(self, statement: str) -> MockResult:
        query = statement
        self._log(query)
        state = self._load()
        for needle, message in state.get("failures", {}).items():
            if needle in query:
                raise Error(message)
        result = self._dispatch(query, state)
        self._save(state)
        return result

    def _dispatch(self, query: str, state: dict[str, Any]) -> MockResult:
        stripped = query.strip()
        roles: dict[str, dict[str, list[str]]] = state["roles"]

        if stripped == "SELECT current_user":
            return MockResult([(self._user(state),)])
        if stripped.startswith("SHOW ROLES TO USER "):
            return MockResult([
                (role, "preset" if role in {"admin", "explorer"} else "custom", True, None)
                for role in state.get("user_roles", ["admin"])
            ])
        if stripped.startswith("SHOW ROLES TO ROLE "):
            role = roles.get(_ident(query, r"TO ROLE "), {})
            return MockResult([(name, "custom", True, None) for name in role.get("included", [])])
        if stripped.startswith("SHOW USERS OF ROLE "):
            role = roles.get(_ident(query, r"OF ROLE "), {})
            return MockResult([(user,) for user in role.get("users", [])])
        if "md_list_roles()" in query:
            return MockResult([(name,) for name in roles])
        if stripped.startswith("CREATE ROLE IF NOT EXISTS "):
            roles.setdefault(_ident(query, r"EXISTS "), {"included": [], "users": []})
            return MockResult([])
        role_grant = re.fullmatch(r"(GRANT|REVOKE) ROLE " + IDENT + r" (?:TO|FROM) (ROLE|USER) " + IDENT + ";", stripped)
        if role_grant:
            verb, granted, kind, grantee = role_grant.groups()
            role_name, member = (grantee, granted) if kind == "ROLE" else (granted, grantee)
            entry = roles.setdefault(role_name.replace('""', '"'), {})
            values = entry.setdefault("included" if kind == "ROLE" else "users", [])
            member = member.replace('""', '"')
            if verb == "GRANT" and member not in values:
                values.append(member)
            if verb == "REVOKE" and member in values:
                values.remove(member)
            return MockResult([])

        if "md_list_share_grantees(" in query:
            share = _string(query, r"md_list_share_grantees\(")
            return MockResult([tuple(row) for row in state["share_grantees"].get(share, [])])
        share_grant = re.fullmatch(
            r"(GRANT|REVOKE) READ ON SHARE " + IDENT + r" (?:TO|FROM) (ROLE|USER) " + IDENT + ";", stripped,
        )
        if share_grant:
            verb, share, kind, grantee = share_grant.groups()
            rows = state["share_grantees"].setdefault(share.replace('""', '"'), [])
            row = [grantee.replace('""', '"'), kind.lower()]
            if verb == "GRANT" and row not in rows:
                rows.append(row)
            if verb == "REVOKE" and row in rows:
                rows.remove(row)
            return MockResult([])
        if stripped.startswith("ALTER SHARE "):
            share = _ident(query, r"ALTER SHARE ")
            state["share_patterns"][share] = _optional_string(query, r"SET INCLUDE_PATTERN ")
            return MockResult([])

        if "MD_ALL_DATABASES()" in query:
            name = _string(query, r"lower\(alias\) = lower\(")
            return MockResult([(db,) for db in state["databases"] if db.lower() == name.lower()])
        if "pragma_version()" in query:
            return MockResult([(state.get("duckdb_version", "v1.5.6"),)])

        if "MD_LIST_DATABASE_SHARES" in query:
            return self._list_share(query, state)
        if "MD_LIST_FLIGHT_RUNS" in query:
            flight_id = _string(query, r"flight_id := ")
            run = int(state["runs"].get(flight_id, 0))
            status = os.environ.get("MOCK_FLIGHT_RUN_STATUS", "RUN_STATUS_SUCCEEDED")
            offset = re.search(r'"offset" := (\d+)', query)
            first_page = not offset or offset.group(1) == "0"
            return MockResult([(run, status)] if run and first_page else [])
        if "MD_LIST_FLIGHTS" in query:
            rows = [(flight_id, str(flight["name"])) for flight_id, flight in state["flights"].items()]
            if os.environ.get("MOCK_DUPLICATE_FLIGHTS", "false") == "true":
                name = "wikipedia-pageviews:feature/mock-test (Preview)"
                rows = [("00000000-0000-0000-0000-000000000011", name), ("00000000-0000-0000-0000-000000000012", name)]
            return _page(query, rows)
        if "MD_LIST_DIVES" in query:
            rows = [(dive_id, str(dive["title"]), dive.get("status")) for dive_id, dive in state["dives"].items()]
            if os.environ.get("MOCK_DUPLICATE_DIVES", "false") == "true":
                title = "Wikipedia Pageviews:feature/mock-test (Preview)"
                rows = [
                    ("00000000-0000-0000-0000-000000000021", title, "draft"),
                    ("00000000-0000-0000-0000-000000000022", title, "draft"),
                ]
            return _page(query, rows)
        if "MD_LIST_GUIDES" in query:
            return _page(query, [
                (guide_id, str(guide["title"]), guide.get("topic")) for guide_id, guide in state["guides"].items()
            ])

        if "MD_CREATE_FLIGHT" in query:
            flight_id = self._new_id(state, 0)
            state["flights"][flight_id] = {
                "name": _string(query, r'"name" => '),
                "owner": self._user(state),
                "schedule": _optional_string(query, r'"schedule_cron" => ') or "",
            }
            return MockResult([])
        if "MD_UPDATE_FLIGHT" in query:
            flight = self._flight(state, _string(query, r'"flight_id" => '))
            schedule = _optional_string(query, r'"schedule_cron" => ')
            if schedule == "" and not flight.get("schedule"):
                raise Error("Invalid Input Error: Cannot clear schedule: Flight has no schedule")
            if schedule is not None:
                flight["schedule"] = schedule
            flight["name"] = _string(query, r'"name" => ')
            return MockResult([])
        if "MD_RUN_FLIGHT" in query:
            if '"config" =>' not in query or '"flight_id" =>' not in query:
                raise Error("MD_RUN_FLIGHT must be called with named config and flight_id arguments")
            flight_id = _string(query, r'"flight_id" => ')
            self._flight(state, flight_id)
            state["runs"][flight_id] = int(state["runs"].get(flight_id, 0)) + 1
            return MockResult([(str(state["runs"][flight_id]),)])
        if "MD_GET_FLIGHT_RUN" in query:
            return MockResult([(os.environ.get("MOCK_FLIGHT_RUN_STATUS", "SUCCEEDED"),)])
        if "MD_GET_FLIGHT_LOGS" in query:
            return MockResult([('{"line":"mock failure log tail","line_number":1}',)])
        if "MD_DELETE_FLIGHT" in query:
            if '"flight_id" =>' not in query:
                raise Error("MD_DELETE_FLIGHT must be called with a named flight_id argument")
            flight_id = _string(query, r'"flight_id" => ')
            state["flights"].pop(flight_id, None)
            state["runs"].pop(flight_id, None)
            return MockResult([])
        if "MD_GET_FLIGHT(" in query:
            flight_id = _string(query, r"flight_id := ")
            return self._by_id(query, flight_id, self._flight(state, flight_id), {"flight_id": flight_id})

        if "MD_DROP_DATABASE_SHARE" in query:
            name = _string(query, r"MD_DROP_DATABASE_SHARE\(")
            shares = state.get("shares")
            if isinstance(shares, dict):
                if name not in shares:
                    raise Error(f'Catalog Error: Share with name "{name}" does not exist!')
                shares.pop(name)
            return MockResult([])
        if stripped.startswith("DROP DATABASE IF EXISTS "):
            name = _ident(query, r"EXISTS ")
            state["databases"] = [db for db in state["databases"] if db.lower() != name.lower()]
            return MockResult([])

        if "MD_CREATE_DIVE" in query:
            dive_id = self._new_id(state, 100)
            state["dives"][dive_id] = {
                "title": _string(query, r"MD_CREATE_DIVE\(title = "),
                "status": "draft",
                "owner": self._user(state),
            }
            return MockResult([(dive_id,)])
        if "MD_UPDATE_DIVE" in query:
            dive_id = _string(query, r"\(id = ")
            dive = self._dive(state, dive_id)
            if "MD_UPDATE_DIVE_METADATA" in query:
                dive["title"] = _string(query, r"MD_UPDATE_DIVE_METADATA\(id = '[^']*'::UUID, title = ")
            if "MD_UPDATE_DIVE_STATUS" in query and not state.get("ignore_dive_status"):
                dive["status"] = _string(query, r"status = ")
            return MockResult([])
        if "MD_DELETE_DIVE" in query:
            state["dives"].pop(_string(query, r"MD_DELETE_DIVE\(id\s*=\s*"), None)
            return MockResult([])
        if "MD_GET_DIVE(" in query:
            dive_id = _string(query, r"id := ")
            return self._by_id(query, dive_id, self._dive(state, dive_id), {"id": dive_id})

        if "MD_CREATE_GUIDE" in query:
            guide_id = self._new_id(state, 200)
            state["guides"][guide_id] = {
                "title": _string(query, r'"title" := '),
                "topic": _optional_string(query, r'"topic" := '),
                "description": _optional_string(query, r'"description" := ') or "",
                "access": _optional_string(query, r'"access" := ') or "user",
                "content": _read_text_argument(query),
                "external_id": _optional_string(query, r'"external_id" := '),
                "references": _references_literal(query, r'"references" := '),
                "owner": self._user(state),
            }
            return MockResult([(guide_id,)])
        if "MD_GET_GUIDE(" in query and "version_external_id" in query:
            guide_id = _string(query, r"MD_GET_GUIDE\(id := ")
            guide = self._guide(state, guide_id)
            desired = _references_literal(query, r"desired_guide_references = ")
            return MockResult([(
                guide.get("content", ""), guide.get("external_id"),
                _references_json(str(guide.get("references", "[]"))), _references_json(desired),
                guide["title"], guide.get("topic"), guide.get("description"), guide.get("access", "user"),
            )])
        if "MD_UPDATE_GUIDE" in query or "MD_SET_GUIDE_ACCESS" in query:
            return self._update_guide(query, state)
        if "MD_DELETE_GUIDE" in query:
            state["guides"].pop(_string(query, r"MD_DELETE_GUIDE\(id := "), None)
            return MockResult([])
        if "MD_GET_GUIDE(" in query:
            guide_id = _string(query, r"id := ")
            return self._by_id(query, guide_id, self._guide(state, guide_id), {"id": guide_id})

        raise RuntimeError(f"Unexpected fake duckdb query: {query}")

    # -- helpers -------------------------------------------------------------

    def _list_share(self, query: str, state: dict[str, Any]) -> MockResult:
        name = _string(query, r"WHERE name = ")
        shares = state.get("shares")
        if isinstance(shares, dict):
            return MockResult([(shares[name],)] if name in shares else [])
        if os.environ.get("MOCK_SHARE_MISSING", "false") == "true":
            return MockResult([])
        return MockResult([(SHARE_URL,)])

    @staticmethod
    def _flight(state: dict[str, Any], flight_id: str) -> dict[str, Any]:
        if flight_id not in state["flights"]:
            raise Error(f"Flight {flight_id} not found")
        flight: dict[str, Any] = state["flights"][flight_id]
        return flight

    @staticmethod
    def _dive(state: dict[str, Any], dive_id: str) -> dict[str, Any]:
        if dive_id not in state["dives"]:
            raise Error(f"Dive {dive_id} not found")
        dive: dict[str, Any] = state["dives"][dive_id]
        return dive

    @staticmethod
    def _guide(state: dict[str, Any], guide_id: str) -> dict[str, Any]:
        if guide_id not in state["guides"]:
            raise Error(f"Guide {guide_id} does not exist")
        guide: dict[str, Any] = state["guides"][guide_id]
        return guide

    @staticmethod
    def _by_id(query: str, resource_id: str, resource: dict[str, Any], ids: dict[str, str]) -> MockResult:
        values = {**ids, "owner_name": resource.get("owner"), "status": resource.get("status")}
        return MockResult([tuple(values.get(column) for column in _select_columns(query))])

    def _update_guide(self, query: str, state: dict[str, Any]) -> MockResult:
        guide = self._guide(state, _string(query, r'"id" := '))
        if "MD_UPDATE_GUIDE(" in query:
            segment = query[query.index("MD_UPDATE_GUIDE("):]
            guide["content"] = _read_text_argument(query)
            guide["external_id"] = _optional_string(segment, r'"external_id" := ')
            guide["references"] = _references_literal(segment, r'"references" := ')
            guide["versions"] = int(guide.get("versions", 1)) + 1
        if "MD_UPDATE_GUIDE_METADATA(" in query:
            segment = query[query.index("MD_UPDATE_GUIDE_METADATA("):].split(";", 1)[0]
            for field in ("title", "topic", "description"):
                value = _optional_string(segment, f'"{field}" := ')
                if value is not None:
                    guide[field] = value
        if "MD_SET_GUIDE_ACCESS(" in query:
            guide["access"] = _string(query[query.index("MD_SET_GUIDE_ACCESS("):], r'"access" := ')
        return MockResult([])

    def close(self) -> None:
        return None


def connect(database: str, *, config: dict[str, Any] | None = None) -> MockConnection:
    if database != "md:":
        raise RuntimeError(f"unexpected database: {database}")
    return MockConnection(config)
