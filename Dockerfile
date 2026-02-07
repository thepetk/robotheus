FROM registry.access.redhat.com/ubi9/python-312:latest

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

EXPOSE 9185

ENTRYPOINT ["uv", "run", "robotheus"]
