import logging

logging.basicConfig(level=logging.DEBUG)

import multiprocessing as mp

from time import sleep
from picamera import PiCamera


class Camera(object):
    def __init__(self):  # , *args, **kwargs

        logging.info("Initialising camera...")

        camera = PiCamera()
        camera.rotation = 180
        camera.zoom = (0.05, 0.0, 0.75, 0.95)
        camera.resolution = (1024, 768)

        # camera.start_preview()
        self.camera = camera

    def _worker(self, file_path):
        logging.debug("Capture process started")
        self.camera.capture("test.jpg") #, resize=(240, 240)
        logging.debug("Capture process ended")


    def start(self, file_path):
        logging.debug("Start called")
        p = mp.Process(target=self._worker, args=(file_path, ))
        p.start()
        self.p = p

    def join(self):
        logging.debug("Calling join...")
        self.p.join()
        return "test.jpg"
