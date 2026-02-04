.PHONY: run test

run:
	python3 -m uvicorn app.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

test:
	pytest -q

sim-quick:
	python3 -m sim_harness.cli quick --no-openai-coach

sim-quick-openai:
	python3 -m sim_harness.cli quick

sim-extended:
	python3 -m sim_harness.cli extended --no-openai-coach --ignore-expected

sim-extended-openai:
	python3 -m sim_harness.cli extended


