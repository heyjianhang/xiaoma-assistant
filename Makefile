.PHONY: check check-backend check-web check-repository

check: check-backend check-web check-repository

check-backend:
	uv run --project apps/api ruff check --config apps/api/pyproject.toml apps/api/src apps/api/tests scripts
	uv run --project apps/api ruff format --check --config apps/api/pyproject.toml apps/api/src apps/api/tests scripts
	uv run --directory apps/api pytest -q
	PYTHONPATH=apps/api/src uv run --project apps/api python scripts/build_chunk_demo.py --check

check-web:
	pnpm --dir apps/web typecheck
	pnpm --dir apps/web lint
	pnpm --dir apps/web test:citations
	pnpm --dir apps/web test:runs
	pnpm --dir apps/web test:chunking
	pnpm --dir apps/web build

check-repository:
	python3 scripts/check_repository.py
