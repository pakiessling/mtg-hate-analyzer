.PHONY: help install fetch-hate videre-report generate-pdf site clean clean-output

help:
	@echo "MTG Hate Cards - Available Commands"
	@echo "==================================="
	@echo "make install        - Install dependencies using uv"
	@echo "make fetch-hate     - Fetch hate cards per archetype from the Videre API (ARGS='--format modern')"
	@echo "make generate-pdf   - Generate printable PDF from latest hate cards report"
	@echo "make videre-report  - Fetch from Videre API and build the PDF in one step"
	@echo "make site           - Build the static GitHub Pages site from the latest report"
	@echo "make clean-output   - Remove _output directory"
	@echo "make clean          - Remove .venv and cache files"

install:
	uv sync

fetch-hate:
	uv run python scripts/videre_hate.py $(ARGS)

videre-report: fetch-hate generate-pdf

generate-pdf:
	uv run python scripts/generate_pdf_report.py

site:
	uv run python scripts/build_site.py

clean-output:
	@if [ ! -f "pyproject.toml" ]; then echo "Error: pyproject.toml not found. Run from project root."; exit 1; fi
	@if [ ! -d "mtgscrap" ]; then echo "Error: mtgscrap module directory not found. Wrong repo."; exit 1; fi
	@if ! git remote -v | grep -q "mtgscrap"; then echo "Error: Not in mtgscrap repository. Remote URL doesn't match."; exit 1; fi
	@if [ -z "$$(git branch --show-current | grep -E '^master$$')" ] && [ -z "$$(git branch --show-current | grep -E '^main$$')" ]; then echo "Error: Not on master/main branch. Refusing to delete _output."; exit 1; fi
	rm -rf _output

clean:
	rm -rf .venv __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
