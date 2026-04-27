"""NBB-905 project read/open semantics."""

from copy import deepcopy

from app.projects.store import ProjectStore


class _Response:
    def __init__(self, data):
        self.data = data


class _FakeProjectTable:
    def __init__(self, project):
        self.project = project
        self.operation = ""
        self.update_payload = None
        self.updates = []

    def select(self, *_args):
        self.operation = "select"
        return self

    def update(self, payload):
        self.operation = "update"
        self.update_payload = payload
        self.updates.append(payload)
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        if self.operation == "update":
            return _Response([{**deepcopy(self.project), **self.update_payload}])
        return _Response([deepcopy(self.project)])


class _FakeSupabase:
    def __init__(self, project):
        self.table_obj = _FakeProjectTable(project)

    def table(self, _name):
        return self.table_obj


def _project_store(project):
    store = ProjectStore.__new__(ProjectStore)
    store.table = "projects"
    store.supabase = _FakeSupabase(project)
    return store


def test_get_project_is_read_only() -> None:
    store = _project_store(
        {
            "id": "proj-1",
            "user_id": "user-1",
            "role": "owner",
            "name": "Project",
            "last_accessed": "old",
        }
    )

    project = store.get_project("proj-1", user_id="user-1")

    assert project["last_accessed"] == "old"
    assert store.supabase.table_obj.updates == []


def test_open_project_is_only_last_accessed_mutation_path() -> None:
    store = _project_store(
        {
            "id": "proj-1",
            "user_id": "user-1",
            "role": "owner",
            "name": "Project",
            "description": "",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "last_accessed": "old",
        }
    )

    project = store.open_project("proj-1", user_id="user-1")

    assert project["last_accessed"] != "old"
    assert list(store.supabase.table_obj.updates[0]) == ["last_accessed"]


def test_project_access_uses_explicit_membership_role() -> None:
    store = _project_store(
        {
            "id": "proj-1",
            "user_id": "owner-1",
            "role": "viewer",
            "name": "Project",
        }
    )

    assert store.has_project_access("proj-1", "viewer-1") is True
    assert store.can_edit_project("proj-1", "viewer-1") is False
    assert store.can_manage_project("proj-1", "viewer-1") is False


def test_viewer_cannot_update_project_metadata() -> None:
    store = _project_store(
        {
            "id": "proj-1",
            "workspace_id": "workspace-1",
            "user_id": "owner-1",
            "role": "viewer",
            "name": "Project",
            "description": "",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "last_accessed": "old",
        }
    )

    try:
        store.update_project("proj-1", name="New name", user_id="viewer-1")
    except PermissionError as exc:
        assert str(exc) == "Project editor role required"
    else:
        raise AssertionError("viewer update should fail")
