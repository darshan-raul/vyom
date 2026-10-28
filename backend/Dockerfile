# Vyom API image (S1.7). Build context is backend/. Built by scripts/vyom-up.sh.
# The base image is pinned by digest in scripts/vyom-up.sh through --build-arg.
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ${PYTHON_IMAGE} AS build
# uv installs exactly what uv.lock pins; its own version is pinned here.
RUN pip install --no-cache-dir uv==0.11.16
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --no-python-downloads
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-python-downloads

FROM ${PYTHON_IMAGE}
# Numeric user so Kubernetes can check runAsNonRoot without a name lookup.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin vyom
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8000
# VYOM_MODE and VYOM_CONFIG come from the deployment; with no mode set the app is production
# and refuses to start (see vyom.api.app).
CMD ["uvicorn", "vyom.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
