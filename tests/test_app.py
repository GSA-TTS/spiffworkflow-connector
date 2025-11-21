from unittest.mock import patch, MagicMock
from falcon import testing


class TestFalconApp:
    def test_liveness_endpoint(self, client: testing.TestClient):
        """Test the liveness endpoint returns expected response"""
        result = client.simulate_get("/liveness")
        assert result.status_code == 200
        assert result.json == {"status": "ok"}

    def test_v1_commands_endpoint(self, client: testing.TestClient):
        """Test the commands endpoint returns list of embedded connectors"""
        result = client.simulate_get("/v1/commands")
        assert result.status_code == 200

        response_data = result.json
        assert isinstance(response_data, list)
        assert len(response_data) > 0

        # Check that artifacts commands are included
        command_ids = [cmd["id"] for cmd in response_data]
        assert "artifacts/GenerateArtifact" in command_ids
        assert "artifacts/GetLinkToArtifact" in command_ids

    def test_nonexistent_endpoint(self, client: testing.TestClient):
        """Test that nonexistent endpoints return 404"""
        result = client.simulate_get("/nonexistent")
        assert result.status_code == 404

    def test_cors_enabled(self, client: testing.TestClient):
        """Test that CORS is enabled"""
        result = client.simulate_options("/liveness")
        # CORS should be handled by Falcon's built-in CORS support
        assert result.status_code in [200, 204]
