FROM python:3.14.6-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/novamind

WORKDIR /app

RUN groupadd --system --gid 10001 novamind \
    && useradd --system --uid 10001 --gid 10001 --create-home \
       --home-dir /home/novamind --shell /usr/sbin/nologin novamind

COPY requirements-linux.txt ./requirements-linux.txt
RUN python -m pip install --no-cache-dir -r requirements-linux.txt \
    && python -m pip check

COPY --chown=10001:10001 mod_chatbot_frontend.py ./
COPY --chown=10001:10001 novamind ./novamind
COPY --chown=10001:10001 services ./services
COPY --chown=10001:10001 utils ./utils
COPY --chown=10001:10001 novamind-logo.png ./novamind-logo.png
COPY --chown=10001:10001 .streamlit/config.toml ./.streamlit/config.toml

# Fail the image build if an application package or runtime dependency is missing.
RUN python -c "import utils.validators; import novamind.ui.app; import services.attachment_store"

USER 10001:10001
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2).read()" || exit 1

CMD ["python", "-m", "streamlit", "run", "mod_chatbot_frontend.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
