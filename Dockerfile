FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends glpk-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY Dashboard.py MultiObjOpt_module.py MultiObjOpt_module_Rail.py MultiObjOpt_module_Maritime.py ./

EXPOSE 8501
CMD ["streamlit", "run", "Dashboard.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]