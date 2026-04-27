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
