from requests import post
from time import sleep, time
from threading import Thread

# import socket
import logging
from sys import exit

# # Fix logging faliure issue
# for handler in logging.root.handlers[:]:
#     logging.root.removeHandler(handler)

# Initialise custom logging format
FORMAT = "%(relativeCreated)6d %(levelname)-8s %(name)s %(process)d %(message)s"
logging.basicConfig(format=FORMAT, level=logging.INFO)
logger = logging.getLogger(__name__)

ip_address = "192.168.0.78"

# testIP = "8.8.8.8"
# s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# s.connect((testIP, 0))
# ip_address = s.getsockname()[0]

ip = "http://" + ip_address + ":5000/"


class SousChef(object):
    def __init__(self):
        self.latest_meta = {}
        self.timers = {}
        self.stop_flag = False
        self.previous_message = "Previous message"
        self.current_message = "Current message"
        self.next_message = "Next message"

        self.step_ID = 1
        self.substep_ID = 1

    def _post(self, data):
        try:
            r = post(ip, data)
            return r
        except:
            logger.info("Connection error")

    def _meta_worker(self):
        while True:
            data = {"action": "get_latest_meta"}
            r = self._post(data)
            try:
                self.latest_meta = dict(r.json())
            except AttributeError:
                pass
            sleep(0.1)

    def _worker(self):
        def _update_screen():
            step_ID = self.step_ID

            try:
                self.previous_message = dispatch_table[step_ID - 1]["message"]
            except KeyError:
                self.previous_message = "Onionbot is connected"

            try:
                self.current_message = dispatch_table[step_ID]["message"]
            except KeyError:
                print("hmmm")

            try:
                self.next_message = dispatch_table[step_ID + 1]["message"]
            except KeyError:
                self.next_message = "Recipe complete!"

        def _classify(args):

            model = args["model"]
            label = args["label"]
            logger.debug("Classifying Model %s | Label %s" % (model, label))

            meta = self.latest_meta
            try:
                data = meta["attributes"]["classification_data"]
                if data[model][label]["boolean"]:
                    logger.debug(
                        "Classifier: " + model + " " + label + " returned true"
                    )

                    # rolling_window = float(meta["attributes"]["interval"]) * 5
                    # logger.info("Sleeping for %s seconds..." % (rolling_window))
                    # sleep(rolling_window)
                    return True
            except KeyError:
                pass
            return False

        def _set_classifiers(args):
            value = args["value"]
            logger.debug("Setting classifiers")
            data = {"action": "set_classifiers", "value": str(value)}
            self._post(data)
            return True

        def _set_fixed_setpoint(args):
            value = args["value"]
            logger.debug("Setting fixed_setpoint")
            data = {"action": "set_fixed_setpoint", "value": str(value)}
            self._post(data)
            return True

        def _set_temperature_target(args):
            value = args["value"]
            logger.debug("Setting temperature_target")
            data = {"action": "set_temperature_target", "value": str(value)}
            self._post(data)
            return True

        def _set_hob_off():
            logger.debug("Turning hob off")
            data = {"action": "set_hob_off"}
            self._post(data)
            return True

        def _start_timer(args):
            name = args["name"]
            duration = float(args["duration"])
            self.timers[name] = time() + duration
            return True

        def _poll_timer(args):
            name = args["name"]
            if time() > self.timers[name]:
                return True
            else:
                return False

        # SPECIAL FUNCTIONS

        def _check_pan():
            def _pan_worker():
                while True:
                    sleep(0.1)
                    try:
                        servo_setpoint = self.latest_meta["attributes"]["servo_setpoint"]
                    except KeyError:
                        pass
                    else:
                        if _classify({"model": "pan_on_off", "label": "pan_off"}):
                            logger.info("No pan detected")
                            while True:
                                sleep(0.1)
                                if _classify({"model": "pan_on_off", "label": "pan_off"}):
                                    _set_hob_off()
                                    self.previous_message = ""
                                    self.current_message = "Return pan to hob to continue"
                                    self.next_message = ""
                                else:
                                    logger.info("Pan detected")
                                    _set_fixed_setpoint({"value": servo_setpoint})
                                    break
            Thread(target=_pan_worker, daemon=True).start()

        # Import recipe from file
        with open("recipes.py", "r") as file:
            data = file.read().replace("\n", "")
        dispatch_table = eval(data)
        self.dispatch_table = dispatch_table

        while True:
            result = False
            logger.info("Step %s | Substep %s" % (self.step_ID, self.substep_ID))
            while result is False and self.stop_flag is False:
                result = False
                step_ID = self.step_ID
                substep_ID = self.substep_ID

                _check_pan()
                _update_screen()

                substep = dispatch_table[step_ID][substep_ID]

                arguments = substep.get("args")
                if arguments:
                    result = substep["func"](args=arguments)
                else:
                    result = substep["func"]()
                sleep(0.1)

            # Increment all substeps then increment steps
            if self.stop_flag is True:
                break
            elif self.substep_ID + 1 in dispatch_table[self.step_ID].keys():
                self.substep_ID += 1
            elif self.step_ID + 1 in dispatch_table.keys():
                self.step_ID += 1
                self.substep_ID = 1
            else:
                break  # Recipe is complete

    def next(self):
        if self.step_ID + 1 in self.dispatch_table.keys():
            logger.info("Next called")
            self.substep_ID = 1
            self.step_ID += 1

    def previous(self):
        if self.step_ID - 1 in self.dispatch_table.keys():
            logger.info("Previous called")
            self.substep_ID = 1
            self.step_ID -= 1

    def run(self):
        Thread(target=self._meta_worker, daemon=True).start()
        Thread(target=self._worker, daemon=True).start()
