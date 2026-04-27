from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import quote
from unittest.mock import MagicMock, patch

from app.auth.asset_tokens import build_asset_token


AUTH_HEADERS = {"Authorization": "Bearer valid-jwt"}
USER_ID = "user-1"


def _patch_bearer_user() -> AbstractContextManager[Any]:
    supabase = MagicMock()
    supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id=USER_ID, email="user@example.com")
    )
    return patch("app.api.auth.middleware.get_supabase", return_value=supabase)


def test_source_download_denies_cross_user_before_signed_url(
    auth_client,
    auth_required_env,
):
    with _patch_bearer_user(), patch(
        "app.projects.store.project_service.has_project_access",
        return_value=False,
    ) as has_access, patch(
        "app.api.sources.routes.source_service"
    ) as source_service:
        response = auth_client.get(
            "/api/v1/projects/project-2/sources/source-1/download",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 404
    has_access.assert_called_once_with("project-2", USER_ID)
    source_service.get_source_file_url.assert_not_called()


def test_generated_image_asset_token_denies_cross_user_before_storage(
    auth_client,
    auth_required_env,
):
    token = build_asset_token(
        USER_ID,
        auth_client.application.config["SECRET_KEY"],
    )
    with patch(
        "app.projects.store.project_service.has_project_access",
        return_value=False,
    ) as has_access, patch(
        "app.api.sources.content.storage_service"
    ) as storage_service:
        response = auth_client.get(
            f"/api/v1/projects/project-2/ai-images/chart.png?asset_token={quote(token)}",
        )

    assert response.status_code == 404
    has_access.assert_called_once_with("project-2", USER_ID)
    storage_service.download_ai_image.assert_not_called()


def test_studio_asset_token_denies_cross_user_before_storage(
    auth_client,
    auth_required_env,
):
    token = build_asset_token(
        USER_ID,
        auth_client.application.config["SECRET_KEY"],
    )
    with patch(
        "app.projects.store.project_service.has_project_access",
        return_value=False,
    ) as has_access, patch(
        "app.api.studio.videos.storage_service"
    ) as storage_service:
        response = auth_client.get(
            f"/api/v1/projects/project-2/studio/videos/job-1/download/video.mp4?asset_token={quote(token)}",
        )

    assert response.status_code == 404
    has_access.assert_called_once_with("project-2", USER_ID)
    storage_service.download_studio_binary.assert_not_called()


def test_brand_download_uses_authenticated_user_for_asset_lookup(
    auth_client,
    auth_required_env,
):
    with _patch_bearer_user(), patch(
        "app.api.brand.routes.brand_asset_service"
    ) as brand_asset_service, patch(
        "app.api.brand.routes.storage_service"
    ) as storage_service:
        brand_asset_service.get_asset.return_value = None

        response = auth_client.get(
            "/api/v1/brand/assets/asset-2/download",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 404
    brand_asset_service.get_asset.assert_called_once_with(USER_ID, "asset-2")
    storage_service.download_brand_asset.assert_not_called()
