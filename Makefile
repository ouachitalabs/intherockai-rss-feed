help:
	echo TODO

api: install
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

install:
	uv pip install --no-cache-dir --upgrade -r requirements.txt
