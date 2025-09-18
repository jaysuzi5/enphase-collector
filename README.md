# enphase-collector
This is a simple collector that pulls data from the Enphase APIs and loads it to a local database through 
a call to a local API.  The process will pull the current summary, events, and alarms and will be scheduled through
a Kubernetes CRON to run every 10 minutes.

I will be taking a new approach to handling the tokens as they cannot just be renewed every cycle.  The enphase APIs
require that you manually approve when creating an access code the first time.  The access token is good for one day
with the refresh token being good for 30 days.  However, when you refresh, you get a new access token and refresh 
token.  Therefore, you will not require manual approval unless the refresh token is stall or you add a brand new
access token.  

The strategy will be to refresh the access token every 12 hours to be safe and store the updated access and refresh
token.  Since this will be running on Kubernetes, I will read direct and update direct from a Kubernetes secret.  I 
will NOT send them in through an environment variable.  This approach may not work for you if you are cloning this 
code and you would need to adjust the code accordingly.

This code will also use my local enphase API which exposes the CRUD operations around a Postgres database that I
will be storing the data in.  See that repo for additional details. https://github.com/jaysuzi5-organization/enphase

## Project Structure

```bash
.
├── Dockerfile
├── requirements.txt
├── src/
│   └── enphase-collector.py
│   └──configuration/
│      └── configuration.yaml
└── .env
```

## .env
The following environment variables need to be defined, these can be in an .env file.  

```bash
ENPHASE_BASE_URL='https://api.enphaseenergy.com/'
ENPHASE_API_URL = 'api/v4/systems/{SYSTEM_ID}/'
LOCAL_API_BASE_URL='http://enphase.dev.svc.cluster.local:5001/api/v1/enphase/'
SYSTEM_ID='1234'
```

## Error Handling

There is no specific retry logic at this time. If there are errors with one session, this should be logged and it will
retry the same pull for a full 24 hours. 

## Traces, Logs, and Metrics

Logs are exposed as OpenTelemetry.  When running locally, the collector will capture Traces to Tempo, Logs to Splunk, 
and metrics to Prometheus. 

## Docker File

```bash
docker login
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t jaysuzi5/enphase-collector:latest \
  --push .
```
