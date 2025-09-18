import requests
import os
import traceback
from dotenv import load_dotenv
from jTookkit.jLogging import LoggingInfo, Logger, EventType
from jTookkit.jConfig import Config
from enphase import Enphase


class EnphaseCollector:

    def __init__(self, config):
        self._config = config
        logging_info = LoggingInfo(**self._config.get("logging_info", {}))
        self._logger = Logger(logging_info)
        self._local_api_base_url = os.getenv("LOCAL_API_BASE_URL")
        self._transaction = None

    def process(self):
        payload = {
        }
        self._transaction = self._logger.transaction_event(EventType.TRANSACTION_START)
        payload['return_code'] = 200

        # Create the Enphase object that will be used to call the external Enphase APIs
        enphase = Enphase(self._config, self._logger, self._transaction)
        enphase_return_code, data = enphase.process()
        if enphase_return_code == 200:
            self._load_data(data, payload)
        else:
            payload['message'] = 'Issue calling Enphase'
            payload['return_code'] = 500
        return_code = payload['return_code']
        payload.pop('return_code')
        self._logger.transaction_event(EventType.TRANSACTION_END, transaction=self._transaction,
                                       payload=payload, return_code=return_code)

    def _load_data(self, data: dict, payload: dict) -> None:
        payload['return_code'] = 200
        response = None
        source_transaction = self._logger.transaction_event(EventType.SPAN_START, payload=payload,
                                                            source_component="enphase: Local Insert",
                                                            transaction=self._transaction)
        try:
            response = requests.post(self._local_api_base_url, json=data)
            response.raise_for_status()
            payload['inserted'] = 1
        except Exception as ex:
            payload['return_code']  = 500
            data = {}
            message = f"Exception inserting Enphase data locally"
            payload["message"] = message
            stack_trace = traceback.format_exc()
            if response:
                data['status_code'] = response.status_code
                data['response.text'] = response.text
            self._logger.message(message=message, exception=ex, stack_trace=stack_trace, data=data,
                                 transaction=source_transaction)
        self._logger.transaction_event(EventType.SPAN_END, transaction=source_transaction,
                                       payload=payload, return_code=payload['return_code'] )

def main():
    load_dotenv()
    config = Config()
    collector = EnphaseCollector(config)
    collector.process()

if __name__ == "__main__":
    main()
