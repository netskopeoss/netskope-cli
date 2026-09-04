"""Unit tests for netskope_cli.core.fieldpaths."""

from __future__ import annotations

from netskope_cli.core.fieldpaths import (
    MISSING,
    discover_schema,
    expand_field_specs,
    find_unmatched,
    get_path,
    project_records,
    resolve_path,
    schema_rows,
    split_path,
    suggest_fields,
)

# Shapes observed on live tenants.
SCIM_USER = {"id": "1", "userName": "alice", "email": "a@x.com", "active": True, "parentGroups": ["g1", "g2"]}
PUBLISHER = {
    "publisher_name": "SASE-GW",
    "status": "connected",
    "assessment": {"version": "1.2", "hdd_free": 100},
    "capabilities": {"DTLS": True, "EEE": False},
}
NPA_APP = {
    "app_name": "[npm.tcolb.com]",
    "protocols": [{"port": "443", "transport": "tcp"}, {"port": "8443", "transport": "tcp"}],
    "service_publisher_assignments": [{"publisher_name": "P1", "reachability": {"reachable": True}}],
    "reachability": {"reachable": False},
}
CLIENT_STATUS = {
    "_id": "abc",
    "hostname": "LAPTOP-1",
    "host_info": {"hostname": "LAPTOP-1", "os": "Windows", "mac_addresses": ["aa", "bb"]},
    "epdlp": {"criticalErrorsCount": 0},
    "on_premises_detail": [{"config_ip": "10.0.4.1", "match_ip": "10.0.4.1"}],
    "status.count": 7,
    "last_event_timestamp": 1756412345,
}


class TestSplitPath:
    def test_simple(self) -> None:
        assert split_path("a.b.c") == ["a", "b", "c"]

    def test_list_hop_attached(self) -> None:
        assert split_path("a[].b") == ["a[]", "b"]
        assert split_path("a.[].b") == ["a[]", "b"]
        assert split_path("a[0].b") == ["a[0]", "b"]


class TestResolve:
    def test_flat(self) -> None:
        assert get_path(SCIM_USER, "userName") == "alice"
        assert get_path(SCIM_USER, "active") is True

    def test_missing_vs_null(self) -> None:
        assert get_path(SCIM_USER, "nope") is MISSING
        assert get_path({"a": None}, "a") is None
        assert resolve_path(SCIM_USER, "nope") == []

    def test_nested_dict(self) -> None:
        assert get_path(PUBLISHER, "assessment.version") == "1.2"
        assert get_path(PUBLISHER, "capabilities.DTLS") is True
        assert get_path(CLIENT_STATUS, "host_info.hostname") == "LAPTOP-1"

    def test_explicit_list_hop(self) -> None:
        assert get_path(NPA_APP, "protocols[].port") == ["443", "8443"]
        assert get_path(NPA_APP, "service_publisher_assignments[].reachability.reachable") == [True]

    def test_implicit_list_mapping(self) -> None:
        assert get_path(NPA_APP, "protocols.port") == ["443", "8443"]

    def test_index(self) -> None:
        assert get_path(NPA_APP, "protocols[1].port") == "8443"
        assert get_path(NPA_APP, "protocols[-1].port") == "8443"
        assert get_path(NPA_APP, "protocols[5].port") is MISSING

    def test_list_of_scalars_is_a_value(self) -> None:
        assert get_path(SCIM_USER, "parentGroups") == ["g1", "g2"]
        assert get_path(CLIENT_STATUS, "host_info.mac_addresses") == ["aa", "bb"]

    def test_literal_dotted_key_wins(self) -> None:
        assert get_path(CLIENT_STATUS, "status.count") == 7
        assert get_path({"a.b": 1, "a": {"b": 2}}, "a.b") == 1

    def test_underscore_id(self) -> None:
        assert get_path(CLIENT_STATUS, "_id") == "abc"

    def test_non_dict_root(self) -> None:
        assert get_path("text", "a") is MISSING
        assert get_path(None, "a") is MISSING


class TestDiscoverSchema:
    def test_union_order_presence_types(self) -> None:
        records = [
            {"a": 1, "b": {"c": "x"}},
            {"a": None, "d": [1, 2]},
            {"a": 2, "b": {"c": "y", "e": True}},
        ]
        schema = discover_schema(records)
        by_path = {s.path: s for s in schema}
        assert [s.path for s in schema] == ["a", "b", "b.c", "d", "b.e"]
        assert by_path["a"].present == 3
        assert by_path["a"].types == ["int", "null"]
        assert by_path["b"].container is True
        assert by_path["b.c"].present == 2
        assert by_path["b.c"].sample == "x"
        assert by_path["d"].types == ["list[int]"]
        assert by_path["d"].sample == [1, 2]
        assert by_path["b.e"].present == 1

    def test_list_of_dicts_uses_bracket_notation(self) -> None:
        schema = discover_schema([NPA_APP])
        paths = [s.path for s in schema]
        assert "protocols" in paths
        assert "protocols[].port" in paths
        assert "service_publisher_assignments[].reachability.reachable" in paths
        assert next(s for s in schema if s.path == "protocols").container is True
        assert next(s for s in schema if s.path == "protocols").type_label == "list[object]"

    def test_present_counts_records_not_elements(self) -> None:
        schema = discover_schema([NPA_APP, NPA_APP])
        port = next(s for s in schema if s.path == "protocols[].port")
        assert port.present == 2

    def test_ignores_non_dict_records(self) -> None:
        assert discover_schema(["x", 1, None]) == []


class TestExpandAndProject:
    def test_glob_expansion_keeps_order_and_dedups(self) -> None:
        schema = discover_schema([CLIENT_STATUS])
        paths, unmatched = expand_field_specs(["hostname", "host_info.*", "hostname", "*_timestamp"], schema)
        assert paths == [
            "hostname",
            "host_info.hostname",
            "host_info.os",
            "host_info.mac_addresses",
            "last_event_timestamp",
        ]
        assert unmatched == []

    def test_glob_skips_containers_and_reports_unmatched(self) -> None:
        schema = discover_schema([CLIENT_STATUS])
        paths, unmatched = expand_field_specs(["nothing.*", "on_premises_detail*"], schema)
        assert "on_premises_detail" not in paths
        assert "on_premises_detail[].config_ip" in paths
        assert unmatched == ["nothing.*"]

    def test_glob_brackets_are_literal(self) -> None:
        schema = discover_schema([NPA_APP])
        paths, _ = expand_field_specs(["protocols[].*"], schema)
        assert paths == ["protocols[].port", "protocols[].transport"]

    def test_project_order_and_missing(self) -> None:
        rows = project_records([CLIENT_STATUS, {"hostname": "B"}], ["host_info.os", "hostname"], missing="")
        assert rows == [{"host_info.os": "Windows", "hostname": "LAPTOP-1"}, {"host_info.os": "", "hostname": "B"}]
        assert list(rows[0].keys()) == ["host_info.os", "hostname"]

    def test_project_dict_and_passthrough(self) -> None:
        assert project_records({"a": 1, "b": 2}, ["b"]) == {"b": 2}
        assert project_records("plain", ["b"]) == "plain"
        assert project_records([{"a": 1}, "junk"], ["a"]) == [{"a": 1}]

    def test_find_unmatched(self) -> None:
        assert find_unmatched([CLIENT_STATUS, {"x": 1}], ["hostname", "nope", "x"]) == ["nope"]


class TestSuggestions:
    def test_tail_match_first(self) -> None:
        cands = ["hostname", "host_info.hostname", "host_info.os", "last_event_timestamp"]
        assert suggest_fields("hostnme", cands)[0] == "hostname"
        assert suggest_fields("os", cands) == ["host_info.os"]
        assert suggest_fields("last_seen", cands) == []

    def test_schema_rows_human_and_machine(self) -> None:
        schema = discover_schema([CLIENT_STATUS, {"hostname": "B"}])
        human = schema_rows(schema, total=2, default_fields=["hostname"])
        first = human[0]
        assert first["field"] == "_id"
        assert first["present"] == "50%"
        host = next(r for r in human if r["field"] == "hostname")
        assert host["default"] == "*" and host["present"] == "100%" and host["sample"] == "LAPTOP-1"
        machine = schema_rows(schema, total=2, default_fields=["hostname"], machine=True)
        mhost = next(r for r in machine if r["field"] == "hostname")
        assert mhost == {
            "field": "hostname",
            "type": "str",
            "present_pct": 100,
            "sample": "LAPTOP-1",
            "in_default": True,
        }
