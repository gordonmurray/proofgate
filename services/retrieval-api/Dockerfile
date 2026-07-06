# retrieval-api runtime image.
# Same image runs staging and prod; behaviour is driven entirely by environment.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The build backend needs the package source present to resolve requirements, so
# copy pyproject + the app package together, then install.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# The demo corpus that ships in the image (loaded at runtime, not part of the wheel).
COPY corpus ./corpus

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
