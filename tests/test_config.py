from robotheus.config import Config


class TestConfigFromEnv:
    def test_defaults(self, monkeypatch: "object") -> "None":
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
        config = Config.from_env()
        assert config.openai_api_key == ""
        assert config.openai_org_id == ""

    def test_reads_env_vars(self, monkeypatch: "object") -> "None":
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.setenv("OPENAI_ORG_ID", "org-abc")
        config = Config.from_env()
        assert config.openai_api_key == "sk-test-123"
        assert config.openai_org_id == "org-abc"


class TestOpenaiEnabled:
    def test_enabled_when_key_set(self) -> "None":
        config = Config(openai_api_key="sk-test")
        assert config.openai_enabled is True

    def test_disabled_when_key_empty(self) -> "None":
        config = Config(openai_api_key="")
        assert config.openai_enabled is False
