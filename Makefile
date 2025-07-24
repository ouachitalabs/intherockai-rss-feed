help:
	echo TODO

api: install
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

install:
	uv pip install --no-cache-dir --upgrade -r requirements.txt

openapi:
	uv run python -c "from api.main import app; import json; spec = app.openapi(); spec['servers'] = [{'url': 'https://services.ouachitalabs.com/api', 'description': 'Production server'}]; print(json.dumps(spec, indent=2))" > openapi.json
