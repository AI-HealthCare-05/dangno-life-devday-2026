import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  \w|^volumes:|^networks:|\Z)", compose, re.M | re.S)
    assert match, f"service not found: {name}"
    return match.group(0)


def test_production_compose_keeps_data_and_application_services_private() -> None:
    compose = (ROOT / "infra" / "docker" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for service in ("redis", "qdrant", "mysql", "fastapi", "ai-worker"):
        assert "ports:" not in _service_block(compose, service)
        assert "restart: unless-stopped" in _service_block(compose, service)
    assert '"80:80"' in _service_block(compose, "nginx")
    assert '"443:443"' in _service_block(compose, "nginx")


def test_production_assets_require_migrations_and_rendered_nginx_config() -> None:
    compose = (ROOT / "infra" / "docker" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert 'DB_GENERATE_SCHEMAS: "false"' in compose
    assert "../nginx/runtime/default.conf" in compose
    assert (ROOT / "scripts" / "preflight-production.sh").exists()
    assert (ROOT / "scripts" / "prepare-ec2-release.sh").exists()


def test_all_nginx_entrypoints_allow_photo_upload_multipart_overhead() -> None:
    configs = (
        "infra/nginx/default.conf",
        "infra/nginx/prod_http.conf",
        "infra/nginx/prod_https.conf",
        "infra/nginx/prod_http.conf.template",
        "infra/nginx/prod_https.conf.template",
        "infra/nginx/ec2-http.conf.template",
    )
    for config_path in configs:
        config = (ROOT / config_path).read_text(encoding="utf-8")
        assert "client_max_body_size 10m;" in config, config_path


def test_nginx_serves_game_assets_directly_with_long_lived_cache() -> None:
    configs = (
        "infra/nginx/default.conf",
        "infra/nginx/prod_http.conf",
        "infra/nginx/prod_https.conf",
        "infra/nginx/prod_http.conf.template",
        "infra/nginx/prod_https.conf.template",
        "infra/nginx/ec2-http.conf.template",
    )
    for config_path in configs:
        config = (ROOT / config_path).read_text(encoding="utf-8")
        assert "location /static/assets/" in config, config_path
        assert "alias /usr/share/nginx/html/static/assets/;" in config, config_path
        assert "expires 30d;" in config, config_path
        assert "access_log off;" in config, config_path


def test_release_build_includes_frontend_nginx_image() -> None:
    dockerfile = (ROOT / "infra" / "nginx" / "Dockerfile").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build-release-images.sh").read_text(encoding="utf-8")
    production_compose = (ROOT / "infra" / "docker" / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "COPY ./src/frontend /usr/share/nginx/html/static" in dockerfile
    assert "web-$APP_VERSION" in build_script
    assert ":web-${APP_VERSION" in production_compose
