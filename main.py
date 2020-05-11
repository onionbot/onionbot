from threading import Thread, Event
from time import sleep

from thermal_camera import ThermalCamera
from camera import Camera
from cloud import Cloud
from inference import Classify
from control import Control
from data import Data
from config import Config

from datetime import datetime
from json import dumps
import logging

# Fix logging faliure issue
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

FORMAT = "%(relativeCreated)6d %(levelname)-8s %(name)s %(process)d %(message)s"
logging.basicConfig(format=FORMAT, level=logging.INFO)
logger = logging.getLogger(__name__)

config = Config()
cloud = Cloud()
thermal = ThermalCamera()
camera = Camera()
control = Control()
data = Data()


class OnionBot(object):
    def __init__(self):

        self.quit_event = Event()

        # Launch multiprocessing threads
        logger.info("Launching worker threads")
        camera.launch()
        thermal.launch()
        control.launch()
        cloud.launch_camera()
        cloud.launch_thermal()

        self.latest_meta = " "
        self.session_ID = None
        self.label = None

    def run(self):
        """Start logging"""

        def _worker():
            """Threaded to run capture loop in background while allowing other processes to continue"""

            measurement_ID = 0
            file_data = None
            meta = None

            while True:

                # Get time stamp
                timer = datetime.now()

                # Get update on key information
                measurement_ID += 1
                label = self.label
                session_ID = self.session_ID

                # Generate file_data for logs
                queued_file_data = data.generate_file_data(
                    session_ID, timer, measurement_ID, label
                )

                # Generate metadata for frontend
                queued_meta = data.generate_meta(
                    session_ID=session_ID,
                    timer=timer,
                    measurement_ID=measurement_ID,
                    label=label,
                    file_data=queued_file_data,
                    thermal_data=thermal.data,
                    control_data=control.data,
                )

                # Start sensor capture
                camera.start(queued_file_data["camera_file"])
                thermal.start(queued_file_data["thermal_file"])

                # While taking a picture, process previous data in meantime
                if file_data:

                    cloud.start_camera(file_data["camera_file"])
                    cloud.start_thermal(file_data["thermal_file"])

                    # inference.start(previous_meta)

                    # Wait for all meantime processes to finish

                    cloud.join_camera()
                    cloud.join_thermal()

                    # if not cloud.join():
                    #     meta["attributes"]["camera_filepath"] = "placeholder.png"
                    #     meta["attributes"]["thermal_filepath"] = "placeholder.png"
                    # inference.join()

                    # Push meta information to file level for API access
                    self.labels_csv_filepath = file_data["label_file"]
                    self.latest_meta = dumps(meta)

                # Wait for queued image captures to finish, refresh control data
                thermal.join()
                camera.join()
                control.refresh(thermal.data["temperature"])

                # Log to console
                if meta is not None:
                    attributes = meta["attributes"]
                    logger.info(
                        "Logged %s | session_ID %s | Label %s | Interval %0.2f | Temperature %s | PID enabled: %s | PID components: %0.1f, %0.1f, %0.1f "
                        % (
                            attributes["measurement_ID"],
                            attributes["session_ID"],
                            attributes["label"],
                            attributes["interval"],
                            attributes["temperature"],
                            attributes["pid_enabled"],
                            attributes["p_component"],
                            attributes["i_component"],
                            attributes["d_component"],
                        )
                    )

                # Move queue forward one place
                file_data = queued_file_data
                meta = queued_meta

                # Add delay until ready for next loop
                frame_interval = float(config.get_config("frame_interval"))
                while True:
                    if (datetime.now() - timer).total_seconds() > frame_interval:
                        break
                    elif self.quit_event.is_set():
                        break
                    sleep(0.1)

                # Check quit flag
                if self.quit_event.is_set():
                    logger.debug("Quitting main thread...")
                    break

        # Start thread
        self.thread = Thread(target=_worker, daemon=True)
        self.thread.start()

    def start(self, session_ID):
        data.start_session(session_ID)
        self.session_ID = session_ID
        return "1"

    def stop(self):
        """Stop logging"""
        self.session_ID = None
        labels = self.labels_csv_filepath
        cloud.start_camera(labels)
        cloud.join_camera()
        return cloud.get_public_path(labels)

    def get_latest_meta(self):
        """Returns cloud filepath of latest meta.json - includes path location of images"""
        return self.latest_meta

    def get_thermal_history(self):
        """Returns last 300 temperature readings"""
        return self.thermal_history

    def get_chosen_labels(self):
        """Returns options for labels selected from `all_labels` in new session process"""
        # (Placeholder) TODO: Update to return list of labels that adapts to selected dropdown
        return '[{"ID":"0","label":"discard"},{"ID":"1","label":"water_boiling"},{"ID":"2","label":"water_not_boiling"}]'

    def set_chosen_labels(self, string):
        """Returns options for labels selected from `all_labels` in new session process"""
        self.chosen_labels = string
        return "1"

    def set_label(self, string):
        """Command to change current active label -  for building training datasets"""
        self.label = string
        return "1"

    def set_no_label(self):
        """Command to set active label to None type"""
        self.label = None
        return "1"

    def set_active_model(self, string):
        """Command to change current active model for predictions"""

        if string == "tflite_water_boiling_1":
            self.camera_classifier = Classify(
                labels="models/tflite-boiling_water_1_20200111094256-2020-01-11T11_51_24.886Z_dict.txt",
                model="models/tflite-boiling_water_1_20200111094256-2020-01-11T11_51_24.886Z_model.tflite",
            )
            self.thermal_classifier = Classify(
                labels="models/tflite-boiling_1_thermal_20200111031542-2020-01-11T18_45_13.068Z_dict.txt",
                model="models/tflite-boiling_1_thermal_20200111031542-2020-01-11T18_45_13.068Z_model.tflite",
            )
            self.active_model = string

        return "1"

    def set_fixed_setpoint(self, value):
        """Command to change fixed setpoint"""
        control.update_fixed_setpoint(value)
        return "1"

    def set_temperature_target(self, value):
        """Command to change temperature target"""
        control.update_temperature_target(value)
        return "1"

    def set_temperature_hold(self):
        """Command to hold current temperature"""
        control.hold_temperature()
        return "1"

    def set_hob_off(self):
        """Command to turn hob off"""
        control.hob_off()
        return "1"

    def set_frame_interval(self, value):
        """Command to change camera targe refresh rate"""
        config.set_config("frame_interval", value)
        return "1"

    def get_all_labels(self):
        """Returns available image labels for training"""
        # data = '[{"ID":"0","label":"discard,water_boiling,water_not_boiling"},{"ID":"1","label":"discard,onions_cooked,onions_not_cooked"}]'
        labels = dumps(data.generate_labels())
        return labels

    def get_all_models(self):
        """Returns available models for prediction"""
        data = '[{"ID":"0","label":"tflite_water_boiling_1"}]'
        return data

    def set_pid_enabled(self, enabled):
        control.set_pid_enabled(enabled)
        return "1"

    def set_p_coefficient(self, coefficient):
        control.set_p_coefficient(coefficient)
        return "1"

    def set_i_coefficient(self, coefficient):
        control.set_i_coefficient(coefficient)
        return "1"

    def set_d_coefficient(self, coefficient):
        control.set_d_coefficient(coefficient)
        return "1"

    def set_pid_reset(self):
        control.set_pid_reset()
        return "1"

    def quit(self):
        logger.info("Raising exit flag")
        self.quit_event.set()
        self.thread.join()
        logger.info("Main module quit")
        camera.quit()
        logger.info("Camera module quit")
        thermal.quit()
        logger.info("Thermal module quit")
        cloud.quit()
        logger.info("Cloud module quit")
        control.quit()
        logger.info("Control module quit")
        logger.info("Quit process complete")
