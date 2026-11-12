FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

COPY solution.py consult.py consultant.py prompt.txt contract.py dialogue.py chunks.py retrieve.py llm.py config.py server.py README.md index.html ./
COPY src ./src
COPY styles ./styles

CMD ["python", "-u", "solution.py"]
