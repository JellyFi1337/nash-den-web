from pathlib import Path


def test_caddy_and_backup_do_not_receive_the_env_file() -> None:
    text = Path("/app/compose.prod.yaml").read_text(encoding="utf-8")
    current = ""
    leaked: list[str] = []
    for line in text.splitlines():
        if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":"):
            current = line.strip()[:-1]
        if current in {"caddy", "backup"} and line.strip().startswith("env_file:"):
            leaked.append(current)
    assert leaked == []
    assert "SITE_DOMAIN:" in text
    assert "PGPASSWORD:" in text


def test_http_mode_publishes_only_port_80_and_plain_cookies() -> None:
    text = Path("/app/compose.http.yaml").read_text(encoding="utf-8")
    assert "ports: !override" in text
    assert '- "80:80"' in text
    assert "443" not in text
    assert text.count('DJANGO_SECURE_COOKIES: "0"') == 2
    assert text.count('DJANGO_HSTS_SECONDS: "0"') == 2
    assert "/etc/caddy/Caddyfile.http" in text
    caddy = Path("/app/docker/caddy/Caddyfile.http").read_text(encoding="utf-8")
    assert "auto_https off" in caddy
    assert ":80 {" in caddy
    dockerfile = Path("/app/docker/caddy/Dockerfile").read_text(encoding="utf-8")
    assert "Caddyfile.http" in dockerfile
