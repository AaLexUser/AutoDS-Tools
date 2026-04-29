# ── Linting & Formatting ─────────────────────────────────────

# Run ruff linter
lint:
    uv run ruff check src/ tests/

# Run ruff formatter (check only)
fmt-check:
    uv run ruff format --check src/ tests/

# Run ruff formatter (write changes)
fmt:
    uv run ruff format src/ tests/

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix src/ tests/

# ── Type Checking ───────────────────────────────────────────

# Run ty type checker
ty:
    uv run ty check

# ── Testing ──────────────────────────────────────────────────

# Run tests
test *FLAGS:
    uv run pytest -v {{FLAGS}}

# ── All Checks ───────────────────────────────────────────────

# Run all checks (lint, format, typecheck, test)
check:
    just lint
    just fmt-check
    just ty
    just test

# ── Miscellaneous ────────────────────────────────────────────

# Run the pygrad CLI
cli *FLAGS:
    uv run pygrad {{FLAGS}}

# Clean build artifacts
clean:
    rm -rf .ruff_cache/ .pytest_cache/ .mypy_cache/ .ty_cache/ *.egg-info/
