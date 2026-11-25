# Development commands for Windows.
# ASCII only: Windows PowerShell 5.1 reads a no-BOM file as cp1251.
param(
    [Parameter(Position = 0)]
    [string]$Command = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if ($null -eq $Rest) {
    $Rest = @()
}

function Exit-OnFailure {
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

switch ($Command) {
    "up" {
        if (-not (Test-Path -LiteralPath ".env")) {
            Copy-Item -LiteralPath ".env.example" -Destination ".env"
            Write-Host "Created .env from .env.example"
        }
        & docker compose up -d --build --wait
        Exit-OnFailure
    }
    "down" {
        & docker compose --profile bot down
        Exit-OnFailure
    }
    "logs" {
        & docker compose --profile bot logs --tail 200
        Exit-OnFailure
    }
    "manage" {
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py @Rest
        Exit-OnFailure
    }
    "test" {
        & docker compose exec web /app/.venv/bin/pytest @Rest
        Exit-OnFailure
    }
    "lint" {
        & docker compose exec web /app/.venv/bin/ruff check src
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/ruff format --check src
        Exit-OnFailure
    }
    "fmt" {
        & docker compose exec web /app/.venv/bin/ruff format src
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/ruff check --fix src
        Exit-OnFailure
    }
    "check" {
        & docker compose exec web /app/.venv/bin/ruff check src
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/ruff format --check src
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/pytest
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py check
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py makemigrations --check --dry-run
        Exit-OnFailure
    }
    "audit" {
        # Runtime packages baked into the image (uv sync --frozen --no-dev).
        # The dev stage adds ruff and pytest only for check; they are not this list.
        $list = Join-Path $env:TEMP "nashden-image-packages.txt"
        & docker run --rm --entrypoint /usr/local/bin/uv nashden-web export --frozen --offline --no-dev --no-emit-project --no-hashes --no-header --no-annotate --directory /app | Set-Content -LiteralPath $list -Encoding ascii
        Exit-OnFailure
        & docker run --rm -v "${list}:/packages.txt:ro" python:3.12-slim-bookworm sh -c "pip install --disable-pip-version-check --root-user-action=ignore -q pip-audit && pip-audit -r /packages.txt"
        Exit-OnFailure
    }
    "demo" {
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py seed_demo --reset
        Exit-OnFailure
    }
    "seed" {
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py seed_demo --reset
        Exit-OnFailure
    }
    "real" {
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py load_private --reset --reports
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py apply_chats_config
        Exit-OnFailure
        & docker compose exec web /app/.venv/bin/python /app/src/manage.py sync_sheet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Sheet sync failed."
        }
    }
    "bot" {
        & docker compose --profile bot up -d bot
        Exit-OnFailure
    }
    "smoke" {
        & docker compose exec web /app/.venv/bin/python /app/scripts/smoke.py @Rest
        Exit-OnFailure
    }
    "deploy" {
        # Server update over SSH: .\dev.ps1 deploy [ssh-host] [project-dir]
        # The host alias comes from ~/.ssh/config (docs/DEPLOY.md, section 1).
        $target = "nashden"
        $dir = "/opt/nash-den"
        if ($Rest.Count -ge 1) { $target = $Rest[0] }
        if ($Rest.Count -ge 2) { $dir = $Rest[1] }
        & ssh $target "bash $dir/scripts/update.sh"
        Exit-OnFailure
    }
    "private" {
        # Upload private/ to the server and reload the schedule: .\dev.ps1 private [ssh-host] [project-dir]
        # Team data is not reset here: load_private --reset stays a manual step (docs/DEPLOY.md, section 9).
        $target = "nashden"
        $dir = "/opt/nash-den"
        if ($Rest.Count -ge 1) { $target = $Rest[0] }
        if ($Rest.Count -ge 2) { $dir = $Rest[1] }
        & scp -r ./private "${target}:${dir}/"
        Exit-OnFailure
        & ssh $target "cd $dir && docker compose exec -T web python /app/src/manage.py load_schedule"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Schedule was not reloaded: check private/schedule.json on the server."
        }
    }
    default {
        Write-Host "Usage: .\dev.ps1 <up|down|logs|manage|test|lint|fmt|check|audit|demo|seed|real|bot|smoke|deploy|private> [args]"
        exit 1
    }
}
