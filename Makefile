.PHONY: setup backend frontend serve test
setup:
	python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env
backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
frontend:
	cd frontend && npm run dev
# The deployed shape: one process, the API serving the built frontend (see Dockerfile and render.yaml).
serve:
	cd frontend && npm run build
	cd backend && FRONTEND_DIST=../frontend/dist .venv/bin/uvicorn app.main:app --port 8000 --workers 1
test:
	cd backend && .venv/bin/pytest -q
