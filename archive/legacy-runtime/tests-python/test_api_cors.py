from __future__ import annotations

import lyra_api


def test_api_cors_allows_tauri_localhost_origin() -> None:
    with lyra_api.app.test_client() as test_client:
        response = test_client.get(
            "/api/health",
            headers={"Origin": "http://tauri.localhost"},
        )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://tauri.localhost"


def test_player_sse_cors_allows_tauri_localhost_origin() -> None:
    with lyra_api.app.test_client() as test_client:
        response = test_client.get(
            "/ws/player",
            headers={"Origin": "http://tauri.localhost"},
        )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://tauri.localhost"
