from datetime import datetime, timezone
from jTookkit.jLogging import Logger, EventType
import base64
import os
import requests
import traceback
from kubernetes import client, config

class Enphase:
    def __init__(self, local_config: dict, logger: Logger, transaction: dict, namespace:str = "collector",
                 secret_name:str = "enphase-tokens", refresh_hours: int = 12):
        self._config = local_config
        self._logger = logger
        self._transaction = transaction
        self._namespace = namespace
        self._secret_name = secret_name
        self._refresh_hours = refresh_hours
        self._user_id = None
        self._api_key = None
        self._client_secret = None
        self._access_token = None
        self._refresh_token = None
        self._enphase_base_url = os.getenv("ENPHASE_BASE_URL")
        api_url = os.getenv("ENPHASE_BASE_URL") + os.getenv("ENPHASE_API_URL")
        self._enphase_api_url = api_url.format(SYSTEM_ID=os.getenv("SYSTEM_ID"))
        config.load_incluster_config()  # works inside K8s
        self._k8s = client.CoreV1Api()

    def process(self):
        overall_return_code = 200
        summary_data = None
        formatted_data = None
        event_data = None
        alarm_data = None
        midnight_ts = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        params = {
            "start_time": midnight_ts
        }
        # Read the secret and set variables
        return_code = self._load_and_refresh_tokens()
        if return_code > overall_return_code:
            overall_return_code = return_code
        # Call the 3 Enphase APIs
        if overall_return_code == 200:
            return_code, summary_data = self._call_api("summary")
            if return_code > overall_return_code:
                overall_return_code = return_code
        if overall_return_code == 200:
            return_code, event_data = self._call_api("events", params)
            if return_code > overall_return_code:
                overall_return_code = return_code
        if overall_return_code == 200:
            return_code, alarm_data = self._call_api("alarms", params)
            if return_code > overall_return_code:
                overall_return_code = return_code
        if overall_return_code == 200:
            formatted_data = Enphase._format_data(summary_data, event_data, alarm_data)
        return overall_return_code, formatted_data

    def _call_api(self, api: str, params=None):
        return_code = 200
        response = None
        return_data = {}
        payload = {}
        url = self._enphase_api_url + api
        payload['url'] = url
        source_transaction = self._logger.transaction_event(EventType.SPAN_START, payload=payload,
                                                            source_component=f"Enphase: {api}",
                                                            transaction=self._transaction)
        try:
            headers = {
                "Authorization": f"Bearer {self._access_token}"
            }
            if not params:
                params = {}
            params["key"] = self._api_key
            params["user_id"] = self._user_id
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return_data = response.json()
        except Exception as ex:
            return_code = 500
            data = {}
            message = f"Exception collecting Enphase data for {api}"
            payload["message"] = message
            stack_trace = traceback.format_exc()
            data["url"] = url
            if response:
                data['status_code'] = response.status_code
                data['response.text'] = response.text
            self._logger.message(message=message, exception=ex, stack_trace=stack_trace, data=data,
                                 transaction=source_transaction)
        self._logger.transaction_event(EventType.SPAN_END, transaction=source_transaction,
                                       payload=return_data, return_code=return_code)
        return return_code, return_data

    @staticmethod
    def _format_data(summary_data, event_data, alarm_data):
        alarm_data_formatted = " | ".join(
            f"id: {alarm['id']}, cleared: {str(alarm['cleared']).lower()}, severity: {alarm['severity']}"
            for alarm in alarm_data.get("alarms", [])
        )
        event_data_formatted = " | ".join(
            f"status: {event['status']}, event_type_id: {event['event_type_id']}"
            for event in event_data.get("events", [])
        )
        data = {
            "system_id": summary_data["system_id"],
            "current_power": summary_data["current_power"],
            "energy_lifetime": summary_data["energy_lifetime"],
            "energy_today": summary_data["energy_today"],
            "last_interval_end_at": summary_data["last_interval_end_at"],
            "last_report_at": summary_data["last_report_at"],
            "modules": summary_data["modules"],
            "operational_at": summary_data["operational_at"],
            "size_w": summary_data["size_w"],
            "status": summary_data["status"],
            "summary_date": summary_data["summary_date"],
            "events": event_data_formatted,
            "alarms": alarm_data_formatted
        }
        return data

    def _get_authorization_code(self):
        # Manually retrieve this code before calling get_access_token
        url = (f"{self._enphase_base_url}oauth/authorize?response_type=code&client_id={self._user_id}"
               f"&redirect_uri={self._enphase_base_url}oauth/redirect_uri")
        print(url)


    def _get_access_token(self, code):
        payload = {}
        return_code = 200
        response = None
        access_token = None
        refresh_token = None
        source_transaction = self._logger.transaction_event(EventType.SPAN_START, payload=payload,
                                                            source_component="Enphase: Access Token",
                                                            transaction=self._transaction)
        try:
            s = f"{self._user_id}:{self._client_secret}"
            basic_auth = base64.b64encode(s.encode("utf-8")).decode("utf-8")
            url = (f"{self._enphase_base_url}oauth/token?grant_type=authorization_code&"
                   f"redirect_uri={self._enphase_base_url}oauth/redirect_uri&code={code}")

            response = requests.post(url, headers={"Authorization": f"Basic {basic_auth}"})
            response.raise_for_status()
            data = response.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            print(f'Access Token: {access_token}')
            print(f'Refresh Token: {refresh_token}')
        except Exception as ex:
            return_code = 500
            data = {}
            if response:
                data['status_code'] = response.status_code
                data['response.text'] = response.text
            message = "Exception calling Enphase to Generate Access Token"
            payload["message"] = message
            stack_trace = traceback.format_exc()
            self._logger.message(message=message, exception=ex, stack_trace=stack_trace, data=data,
                                 transaction=source_transaction)
        self._logger.transaction_event(EventType.SPAN_END, transaction=source_transaction,
                                       payload=payload, return_code=return_code)
        return access_token, refresh_token



    def _refresh_access_token(self):
        payload = {}
        return_code = 200
        source_transaction = self._logger.transaction_event(EventType.SPAN_START, payload=payload,
                                                            source_component="Enphase: Refresh Token",
                                                            transaction=self._transaction)
        access_token = None
        refresh_token = None
        response = None
        try:
            s = f"{self._user_id}:{self._client_secret}"
            basic_auth = base64.b64encode(s.encode("utf-8")).decode("utf-8")
            url = f'{self._enphase_base_url}oauth/token?grant_type=refresh_token&refresh_token={self._refresh_token}'

            response = requests.post(url, headers={"Authorization": f"Basic {basic_auth}"})
            response.raise_for_status()
            data = response.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            print(f'Access Token: {access_token}')
            print(f'Refresh Token: {refresh_token}')
        except Exception as ex:
            return_code = 500
            data = {}
            if response:
                data['status_code'] = response.status_code
                data['response.text'] = response.text
            message = "Exception calling Enphase to Refresh the Token"
            payload["message"] = message
            stack_trace = traceback.format_exc()
            self._logger.message(message=message, exception=ex, stack_trace=stack_trace, data=data,
                                 transaction=source_transaction)
        self._logger.transaction_event(EventType.SPAN_END, transaction=source_transaction,
                                       payload=payload, return_code=return_code)
        return access_token, refresh_token

    @staticmethod
    def _decode(value):
        return base64.b64decode(value).decode("utf-8") if value else None

    def _load_and_refresh_tokens(self):
        payload = {}
        return_code = 200
        source_transaction = self._logger.transaction_event(EventType.SPAN_START, payload=payload,
                                                            source_component="K8s: Read Secret",
                                                            transaction=self._transaction)
        try:
            """Reads secret, sets class vars, refreshes if >12h old, and updates secret if needed."""
            secret = self._k8s.read_namespaced_secret(self._secret_name, self._namespace)
            data = {k: Enphase._decode(v) for k, v in secret.data.items()}

            # 🔹 Set class variables
            self._api_key = data.get("api_key")
            self._user_id = data.get("user_id")
            self._client_secret = data.get("client_secret")
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            last_updated = data.get("last_updated")

            # Check if refresh is needed
            last_dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600

            if age_hours > self._refresh_hours:
                new_access, new_refresh = self._refresh_access_token()

                self._access_token = new_access
                self._refresh_token = new_refresh
                last_updated = datetime.now(timezone.utc).isoformat()

                # Update secret
                secret.string_data = {
                    "api_key": self._api_key,
                    "user_id": self._user_id,
                    "client_secret": self._client_secret,
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "last_updated": last_updated,
                }
                self._k8s.patch_namespaced_secret(self._secret_name, self._namespace, secret)
        except Exception as ex:
            return_code = 500
            message = "Exception getting secret from Kubernetes"
            payload["message"] = message
            stack_trace = traceback.format_exc()
            self._logger.message(message=message, exception=ex, stack_trace=stack_trace, transaction=source_transaction)
        self._logger.transaction_event(EventType.SPAN_END, transaction=source_transaction,
                                       payload=payload, return_code=return_code)
        return return_code
