# kolenke cloud panel: accounts + relay. No Playwright, no user data except accounts.
FROM python:3.12-slim
WORKDIR /app
COPY relay/requirements.txt relay/requirements.txt
RUN pip install --no-cache-dir -r relay/requirements.txt
COPY relay relay
COPY static/index.html static/index.html
ENV RELAY_DATA=/data RELAY_SECURE_COOKIES=1 RELAY_TRUST_PROXY=1
RUN useradd -m kolenke && mkdir -p /data && chown kolenke /data
USER kolenke
EXPOSE 8080
CMD ["uvicorn", "relay.app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--no-access-log"]
