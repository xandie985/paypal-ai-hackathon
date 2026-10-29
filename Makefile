.PHONY: setup backend frontend test
setup:
	python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env
backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
frontend:
	cd frontend && npm run dev
test:
	cd backend && .venv/bin/pytest -q
