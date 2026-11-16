import unittest
from unittest.mock import patch

import tap_jira
from tap_jira import streams
from tap_jira.context import Context

# Streams whose ids repeat across Jira sites; they share one table per stream
# downstream, so their key must include the tenant.
TENANT_SCOPED = {
    "users": ["tenant", "accountId"],
    "projects": ["tenant", "id"],
    "versions": ["tenant", "id"],
    "components": ["tenant", "id"],
    "project_types": ["tenant", "key"],
    "project_categories": ["tenant", "id"],
    "issue_types": ["tenant", "id"],
    "resolutions": ["tenant", "id"],
    "roles": ["tenant", "id"],
    "statuses": ["tenant", "id"],
    "issue_priorities": ["tenant", "id"],
}


class TestTenantScopedKeys(unittest.TestCase):
    def setUp(self):
        self.catalog = tap_jira.discover()
        self.entries = {s.tap_stream_id: s for s in self.catalog.streams}

    def test_discovered_key_properties_include_tenant(self):
        for stream_id, keys in TENANT_SCOPED.items():
            entry = self.entries[stream_id]
            self.assertEqual(entry.key_properties, keys, stream_id)
            self.assertIn("tenant", entry.schema.properties, stream_id)

    def test_records_carry_tenant(self):
        stream = next(s for s in streams.ALL_STREAMS
                      if s.tap_stream_id == "issue_types")
        with patch.object(Context, "config", {"site_name": "acme"}), \
                patch.object(Context, "catalog", self.catalog), \
                patch.object(streams.singer, "write_record") as write_record:
            stream.write_page([{"id": "10001", "name": "Bug"}])

        record = write_record.call_args[0][1]
        self.assertEqual(record["tenant"], "acme")
        self.assertEqual(record["id"], "10001")

    def test_records_carry_tenant_with_catalog_lacking_tenant(self):
        stream = next(s for s in streams.ALL_STREAMS
                      if s.tap_stream_id == "issue_types")
        del self.entries["issue_types"].schema.properties["tenant"]
        with patch.object(Context, "config", {"site_name": "acme"}), \
                patch.object(Context, "catalog", self.catalog), \
                patch.object(streams.singer, "write_record") as write_record:
            stream.write_page([{"id": "10001", "name": "Bug"}])

        self.assertEqual(write_record.call_args[0][1]["tenant"], "acme")
