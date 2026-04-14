from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_server_loads_benchmark_env_file_as_startup_fallback():
    content = (PROJECT_ROOT / "api" / "server.py").read_text(encoding="utf-8")

    assert 'for candidate_name in (".env", ".env.benchmark", ".env.connected")' in content
    assert '_load_startup_env_files()' in content


def test_server_oauth_refresh_checks_benchmark_env_file():
    content = (PROJECT_ROOT / "api" / "server.py").read_text(encoding="utf-8")

    assert '_ENV_ROOT / ".env.benchmark"' in content
    assert '"checked_files": [".env", ".env.benchmark", ".env.connected"]' in content


def test_start_full_stack_supports_benchmark_env_fallback():
    content = (PROJECT_ROOT / "start_full_stack.ps1").read_text(encoding="utf-8")

    assert '".env.benchmark"' in content
    assert 'Using benchmark environment file .env.benchmark' in content
