FROM python:3.12.9-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ /app/src/
ENV ENPHASE_BASE_URL='https://api.enphaseenergy.com/'
ENV ENPHASE_API_URL = 'api/v4/systems/{SYSTEM_ID}/'
ENV LOCAL_API_BASE_URL='http://home.dev.com/api/v1/enphase'
ENV SYSTEM_ID='1234'

CMD ["opentelemetry-instrument", "--logs_exporter", "otlp", "--traces_exporter", "otlp", "python", "/app/src/enphase-collector.py"]