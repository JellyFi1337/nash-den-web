.PHONY: up down logs manage test lint fmt check audit demo seed real bot smoke deploy private

COMPOSE = docker compose
WEB = $(COMPOSE) exec web
PY = /app/.venv/bin/python
RUFF = /app/.venv/bin/ruff
PYTEST = /app/.venv/bin/pytest
# Сервер для deploy и private: псевдоним из ~/.ssh/config и каталог проекта.
HOST ?= nashden
DIR ?= /opt/nash-den

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) --profile bot down

logs:
	$(COMPOSE) --profile bot logs --tail 200

manage:
	$(WEB) $(PY) /app/src/manage.py $(ARGS)

test:
	$(WEB) $(PYTEST)

lint:
	$(WEB) $(RUFF) check src
	$(WEB) $(RUFF) format --check src

fmt:
	$(WEB) $(RUFF) format src
	$(WEB) $(RUFF) check --fix src

check: lint test
	$(WEB) $(PY) /app/src/manage.py check
	$(WEB) $(PY) /app/src/manage.py makemigrations --check --dry-run

audit:
	docker run --rm --entrypoint /usr/local/bin/uv nashden-web export --frozen --offline --no-dev --no-emit-project --no-hashes --no-header --no-annotate --directory /app > /tmp/nashden-image-packages.txt
	docker run --rm -v /tmp/nashden-image-packages.txt:/packages.txt:ro python:3.12-slim-bookworm sh -c "pip install --disable-pip-version-check --root-user-action=ignore -q pip-audit && pip-audit -r /packages.txt"

demo:
	$(WEB) $(PY) /app/src/manage.py seed_demo --reset

seed: demo

real:
	$(WEB) $(PY) /app/src/manage.py load_private --reset --reports
	$(WEB) $(PY) /app/src/manage.py apply_chats_config
	-$(WEB) $(PY) /app/src/manage.py sync_sheet

bot:
	$(COMPOSE) --profile bot up -d bot

smoke:
	$(WEB) $(PY) /app/scripts/smoke.py

deploy:
	ssh $(HOST) "bash $(DIR)/scripts/update.sh"

private:
	scp -r ./private "$(HOST):$(DIR)/"
	-ssh $(HOST) "cd $(DIR) && docker compose exec -T web python /app/src/manage.py load_schedule"
