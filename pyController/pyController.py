
import time
import os
import json
import logging
from logging.handlers import RotatingFileHandler

# factory modules import
import utilities
from job_queue import JobQueue
from job_data import JobData
from inventory import Inventory
from mqtt import Factory_MQTT
import webcam
from factory.factory import FACTORY             # Real factory
from factory.factory_sim2 import FactorySim2    # Simulated factory
from webapp import webadmin


#*********************************************
#* * * * * * * * * Logger Setup * * * * * * * *
#*********************************************

# Logger: logging config   https://docs.python.org/3/howto/logging-cookbook.html
# Create logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG) # sets default logging level for this module

# Create formatter
#formatter = logging.Formatter('[%(asctime)s] [%(levelname)-5s] [%(name)s] [%(threadName)s] - %(message)s')
formatter = logging.Formatter('[%(asctime)s] [%(levelname)-5s] [%(name)s] - %(message)s')

# Logger: create rotating file handler
script_dir = os.path.dirname(os.path.realpath(__file__))    # Directory this script is running from
utilities.create_log_dir(script_dir + "/logs")                    # creates /logs directory if missing
rfh = RotatingFileHandler(script_dir + "/logs/app.log")
rfh.maxBytes = 1024*1024          # maximum size of a log before being rotated
rfh.backupCount = 2               # how many rotated files to keep
rfh.setFormatter(formatter)     # set format
rfh.setLevel(logging.DEBUG)     # set level for file logging
logger.addHandler(rfh)          # add filehandle to logger

# Logger: create console handle
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)     # set logging level for console
ch.setFormatter(formatter)
logger.addHandler(ch)

# reduce logging level of specific libraries
logging.getLogger("jobQueue").setLevel(logging.DEBUG)
logging.getLogger("paho.mqtt.client").setLevel(logging.INFO)
logging.getLogger("Factory_MQTT").setLevel(logging.INFO)
logging.getLogger("Factory").setLevel(logging.DEBUG)
logging.getLogger("pymodbus").setLevel(logging.INFO)



class Orchastrator():
    def __init__(self, mqtt=None, queue=None, inventory=None, factory=None):
        if queue is None:
            raise Exception("queue not specified")
        elif inventory is None:
            raise Exception("inventory not specified")
        elif factory is None:
            raise Exception("factory not specified")

        self.inventory = inventory
        self.queue = queue
        self.factory = factory
        self.mqtt = mqtt  # mqtt is optional

        self.current_job = None
        self.last_factory_state = None


    def add_job_callback(self, job_data):
        """ Add job data to Job queue """
        # Verify
        if not isinstance(job_data, JobData):
            log_msg = f"Invalid new job data. Not job_data object)"
            logging.error("%s", log_msg)

        # Add to queue
        self.queue.add_job(job_data)
        log_msg = f"Added job {job_data.job_id} for order {job_data.order_id} | color: {job_data.color},  cook time: {job_data.cook_time}, sliced: {job_data.sliced}"
        logging.info(log_msg)
        notice_msg = {'msg_type': 'job_status', 'job_id': job_data.job_id, 'message': 'Added to queue'}
        self.send_job_notice(notice_msg)


    def cancel_job_id_callback(self, job_id):
        """ Search job queue and delete matching job id """
        # Verify
        if not (isinstance(job_id, int) and job_id >= 0):
            log_msg = f"Error: Invalid cancel job id: {job_id}"
            logging.error(log_msg)
            notice_msg = {'msg_type': 'error', 'message': "Invalid id"}
            self.send_job_notice(notice_msg)
            return

        # Cancel Job
        canceled_list = self.queue.cancel_job_id(job_id)

        # Report
        if len(canceled_list) > 0:
            log_msg = f"Deleting Job #: {job_id}"
            notice_msg = {'msg_type': 'job_status', 'job_id': job_id, 'message': "Canceled"}
        else:
            log_msg = f"Could not find any jobs matching job_id {job_id} found"
            notice_msg = {'msg_type': 'error', 'message': f"Job id {job_id} not found"}
        logging.debug(log_msg)
        self.send_job_notice(notice_msg)


    def cancel_job_order_callback(self, order_id):
        """ Search job queue and delete all jobs matching order id """
        # Verify
        if not (isinstance(order_id, int) and order_id >= 0):
            log_msg = f"Error: Invalid cancel order id: {order_id}"
            logging.error(log_msg)
            notice_msg = {'msg_type': 'error', 'message': "Invalid id"}
            self.send_job_notice(notice_msg)
            return

        # Cancel order
        canceled_list = self.queue.cancel_job_order(order_id)

        # Report
        if len(canceled_list) > 0:             # If jobs were deleted
            for deleted_job_id in canceled_list:
                log_msg = f"Deleting Job #: {deleted_job_id} from order {order_id}"
                notice_msg = {'msg_type': 'job_status', 'job_id': deleted_job_id, 'message': "Canceled"}
                logging.debug(log_msg)
                self.send_job_notice(notice_msg)
        else:                                  # if no Jobs were canceled
            log_msg = f"Could not find any jobs matching order_id {order_id}"
            notice_msg = {'msg_type': 'error', 'message': f"Order id {order_id} not found"}
            logging.debug(log_msg)
            self.send_job_notice(notice_msg)


    def factory_command_callback(self, command, **args):
        """ Calls factory.command with supplied args """
        logging.debug("Factory command: %s, args: %r", command, args)
        if command == 'reset_inventory':
            self.inventory.preset_inventory()

    def send_inventory(self):
        # Get inventory
        if self.mqtt is not None:
            inv = {}
            inv['Inventory'] = self.inventory.get_inventory()
            logging.info("Inventory: %s", inv['Inventory'])

            self.mqtt.publish('Factory/Inventory', payload=json.dumps(inv), qos=0)
        return


    def send_status(self):
        if self.mqtt is not None:
            status = {}
            status['factory_status'] = self.factory.status()

            if self.current_job is None:
                status['current_job'] = "None"
            else:
                status['current_job'] = str(self.current_job.job_id)

            status['job_queue_len'] = str(self.queue.has_jobs())
            self.mqtt.publish("Factory/Status", payload=json.dumps(status), qos=0)
        return


    def send_job_notice(self, msg):
        if self.mqtt is not None:
            self.mqtt.publish("Factory/Job_notice", payload=json.dumps(msg), qos=2)
        return


    def factory_update(self):
        """Run the factory's update function.
           This should be called every 1-5 seconds"""
        factory_state = self.factory.update()
        logging.debug("Factory state: %s", factory_state)

        # If factory just finished processing
        if factory_state == 'ready' and self.last_factory_state == 'processing':
            # Job finished
            message = f"Job {self.current_job.job_id} has been completed"
            logging.info(message)

            notice_msg = {'msg_type': 'job_status', 'job_id': self.current_job.job_id, 'message': 'Completed'}
            self.send_job_notice(notice_msg)
            self.current_job = None
            self.send_status()

        # If factory ready, start a job if available
        elif factory_state == 'ready' and self.queue.has_jobs():
            logging.info("Starting job")
            self.factory_start_job()

        elif factory_state == 'processing':
            logging.debug("Factory processing...")

        self.last_factory_state = factory_state


    def factory_start_job(self):
        '''Start factory operation'''
        if self.queue.has_jobs:
            # Pop next job
            current_job = self.queue.next_available_job(self.inventory) # returns job or False

            if current_job is False: # No job ready
                logging.debug("Could not match waiting job with available inventory")
                return
            else:
                self.current_job = current_job

            # Send to factory
            self.factory.order(current_job)

            message = f"Started job {current_job.job_id}"
            logging.info(message)

            # Send updated information
            notice_msg = {'msg_type': 'job_status', 'job_id': current_job.job_id, 'message': 'Started'}
            self.send_job_notice(notice_msg)
            self.send_status()
            self.send_inventory()

        return


def main():
    '''pyController main program'''

    logging.info("Starting factory python controller")

    # Signal handler
    killer = utilities.GracefulKiller()

    # Get environment configs
    config = utilities.load_env()

    logging.info("Starting factory MQTT")
    mqtt = Factory_MQTT(URL=config['MQTT_BROKER_URL'], PORT=int(config['MQTT_PORT']),
                                    CLIENT_ID=config['MQTT_CLIENT_ID'], TOPIC_SUB=config['MQTT_SUBSCRIBE'])
    mqtt.connect()
    time.sleep(1)
    mqtt.start()

    logging.debug("Creating Job and orchastrator")

    # Setup Job Queue and Inventory objects
    job_queue = JobQueue()
    inventory = Inventory()
    inventory.preset_inventory()

    # Setup factory object
    logging.debug("Creating factory object")
    if config['FACTORY_SIM'] == 'True': # Use FactorySim2
        logging.info("Using Factory sim")
        factory = FactorySim2(processing_time=30)
    else:
        logging.info("Using Factory Modbus")
        factory = FACTORY(config['FACTORY_IP'], config['FACTORY_PORT'])


    # Setup webcam
    if config['FAKE_WEBCAM'] == 'True':
        logging.debug("Using fake image source")
        my_webcam = webcam.Webcam(rate=10, mqtt=mqtt)
        my_webcam.start()

    else:
        logging.debug("Using real camera")
        my_webcam = webcam.Webcam(rate=10, mqtt=mqtt, source=0)
        my_webcam.start()


    # Setup orchastrator object
    orchastrator = Orchastrator(mqtt=mqtt, queue=job_queue, inventory=inventory, factory=factory)

    # Setup webadmin object
    webadmin.webapp_storage.set_orchastrator(orchastrator)
    webadmin.start_webapp()

    # set mqtt orchastrator callbacks
    mqtt.set_add_job_callback(orchastrator.add_job_callback)
    mqtt.set_cancel_job_callback(orchastrator.cancel_job_id_callback)
    mqtt.set_cancel_order_callback(orchastrator.cancel_job_order_callback)
    mqtt.set_factory_command_callback(orchastrator.factory_command_callback)

    #add_job = JobData(job_id=123, order_id=100, color='white', cook_time=12, sliced=True)
    #orchastrator.add_job_callback(add_job)

    logging.debug("Going into main loop")
    count = 0
    while not killer.kill_now:
        try:
            count += 1
            time.sleep(1)
        except KeyboardInterrupt:
            break

        if count % 2 == 0:
            orchastrator.factory_update()
            mqtt.update()
            my_webcam.update()

        if count % 15 == 0:
            orchastrator.send_status()

        if count % 60 == 0:
            orchastrator.send_inventory()
        
        if count > 600:
            if config['FACTORY_SIM'] == 'True':
                logging.info("Resetting Inventory")
                orchastrator.inventory.preset_inventory()
            count = 0

    # Shutdown
    logging.info("Shutting down gracefully")
    my_webcam.stop()
    factory.stop()
    mqtt.stop()


if __name__ == '__main__':
    main()
