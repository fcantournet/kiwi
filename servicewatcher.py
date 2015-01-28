import json
import logging
import requests
import time
from multiprocessing import Process
from itertools import izip

from utils import iter_lines

default_kube_endpoint = 'http://localhost:8080'


class ServiceWatcher (Process):
    log = logging.getLogger('kiwi.servicewatcher')

    def __init__(self,
                 queue,
                 reconnect_interval=5,
                 kube_endpoint=default_kube_endpoint):
        super(ServiceWatcher, self).__init__()

        self.q = queue
        self.kube_api = '%s/api/v1beta1' % kube_endpoint
        self.reconnect_interval = reconnect_interval

    def run(self):
        while True:
            r = requests.get('%s/watch/services' % self.kube_api, stream=True)
            if r.ok:
                lines = iter_lines(r.raw)
                for datalen, data, marker in izip(lines, lines, lines):
                    try:
                        event = json.loads(data)
                    except ValueError:
                        self.log.error('failed to decode server response')
                        break

                    handler = getattr(self, 'handle_%s' %
                                      event['type'].lower())

                    if not handler:
                        self.log.warn('unknown event: %(type)s' % event)
                        continue

                    handler(event['object'])
            else:
                self.log.error('request failed (%d): %s',
                               r.status_code,
                               r.reason)

            self.log.warn('reconnecting to server')
            time.sleep(self.reconnect_interval)

    def handle_added(self, service):
        self.log.info('added: %s', service)
        self.q.put({'message': 'add-service',
                    'data': {'service': service}})

    def handle_deleted(self, service):
        self.log.info('deleted: %s', service)
        self.q.put({'message': 'delete-service',
                    'data': {'service': service}})

    def handle_modified(self, service):
        self.log.info('modified: %s', service)
        self.q.put({'message': 'update-service',
                    'data': {'service': service}})


if __name__ == '__main__':
    import multiprocessing
    logging.basicConfig(level=logging.DEBUG)

    q = multiprocessing.Queue()
    s = ServiceWatcher(q)
    s.start()

    while True:
        msg = q.get()
        print 'msg:', msg