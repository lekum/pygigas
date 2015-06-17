import logging
import pprint
import requests as r
from time import sleep
from os import environ

class Gigas:
    """
    Models a connection to Gigas API
    """

    def __init__(self, apiuser=None, apipswd=None, api_endpoint="https://api.madrid.gigas.com"):
        """
        Creates the Gigas object given the credentials
        """
        self.api_endpoint = api_endpoint
        self.apiuser = apiuser if apiuser else environ.get("GIGAS_API_USER")
        self.apipswd = apipswd if apipswd else environ.get("GIGAS_API_PASSWORD")
        self.token = ""
        self.headers = {
                        "Authorization": "",
                        "Accept": "application/json"
                       }
        self._update_temporary_token()
        self.auth_retries = 0

    def _wait_for_transaction(self, transaction_id, polling_interval=5, max_retries=24):
        """
        Waits for transaction `transaction_id` to be completed or errored, with
        optional `polling_interval` and `max_retries`
        """
        logging.info("Waiting for transaction_id: %s" % str(transaction_id))
        num_retries = 0

        while (True):
            res = r.get(self.api_endpoint + "/transaction/" + str(transaction_id) + "/status", headers=self.headers)
            logging.info("Status: %s" % str(res.json()))
            if ("error" in res.json()):
                if (res.json()["error"] == "Transaction not found"):
                    logging.warning("Transaction %s not found" % str(transaction_id))
                    return "Not found"
                else:
                    logging.error("Error waiting for transaction %s" % str(transaction_id))
                    return "Error"
            elif (res.json()["status"] == "complete"):
                logging.info("Transaction %s complete" % str(transaction_id))
                return "Complete"
            else:
                logging.info("Status: %s, retry: %i" % (res.json()["status"], num_retries))
                num_retries += 1
                if (num_retries >= max_retries):
                    logging.warning("Too many retries for transaction %s" % str(transaction_id))
                    return "Timeout"
                else:
                    continue

    def _update_temporary_token(self):
        """
        Requests a temporary token and stores it in the headers
        """
        payload = {'login': self.apiuser, 'password': self.apipswd}
        res = r.post(self.api_endpoint + "/token", data=payload)
        self.token = res.json()["token"]
        logging.info("Got token: %s" % self.token)
        self.headers["Authorization"] = "Gigas token=" + self.token

    def create_vm(self, memory, cpus, hostname, label, primary_disk_size, swap_disk_size, template_id):
        """
        Creates the vm with specified values for
          - memory (in mb)
          - cpus
          - label
          - primary_disk_size
          - swap_disk_size
          - template_id
        """
        logging.info("Creating new vm")
        payload = {'memory': memory,
                   'cpus': cpus,
                   'hostname': hostname,
                   'label': label,
                   'primary_disk_size': primary_disk_size,
                   'swap_disk_size': swap_disk_size,
                   'template_id': template_id,
                  }
        res = r.post(self.api_endpoint + "/virtual_machine", data=payload, headers=self.headers)
        if res.status_code == r.codes.unauthorized:
            logging.warning("Unauthorized access to API")
            self.auth_retries += 1
            # Update the token and try again
            if self.auth_retries < 2:
                logging.warning("Requesting a new API token")
                self._update_temporary_token()
                res = r.post(self.api_endpoint + "/virtual_machine", data=payload, headers=self.headers)
            else:
                # Raise a 401
                logging.error("Too many unauthorized access to API")
                res.raise_for_status()
        transaction_id = res.json()["queue_token"]
        logging.info("Creating vm - queue_token: %s" % transaction_id)
        machine_id = res.json()["resource"]["id"]
        transaction_result = self._wait_for_transaction(transaction_id)
        if ((transaction_result == "Complete") or (transaction_result == "Not found")):
            machine_details = self.get_machine_info(machine_id)
            return GigasVM(vm_attributes = machine_details)
        else:
            logging.error("Transaction %s errored" % str(transaction_id))
            return False

    def get_machine_info(self, machine_id):
        """
        Returns a dict with the key/value pairs of a vm attributes
        """
        res = r.get(self.api_endpoint + "/virtual_machine/" + str(machine_id), headers=self.headers)
        vm_attributes = res.json()
        res = r.get(self.api_endpoint + "/virtual_machine/" + str(machine_id) + "/network_interfaces", headers=self.headers)
        interface_ids = (interface["id"] for interface in res.json())
        ip_addresses = []
        for ip in  r.get(self.api_endpoint + "/ip_addresses", headers=self.headers).json():
            if ip["interface_id"] in interface_ids:
                ip_addresses.append(ip["address"])

        vm_attributes["ip_addresses"] = ip_addresses
        logging.info("Attributes of the VM: %s " % str(vm_attributes))
        return vm_attributes

    def delete_vm(self, vm):
        """
        Deletes an existing GigasVM object
        """
        res = r.delete(self.api_endpoint + "/virtual_machine/" + str(vm.id), headers=self.headers)
        transaction_id = res.json()["queue_token"]
        transaction_result = self._wait_for_transaction(transaction_id)
        del vm

class GigasVM:
    """
    Models a Virtual Machine in Gigas environment
    """

    def __init__(self, vm_attributes):
        """
        Copies the attributes in the vm_attributes dict to the instance
        """
        logging.info("Creating vim with attributes")
        logging.info(pprint.pprint(vm_attributes))
        for key,value in vm_attributes.items():
            setattr(self, key, value)

if __name__ == '__main__':

    g = Gigas()
    vm = g.create_vm(memory = 512, cpus = 1, hostname = "test",label = "test-label", primary_disk_size = 20, swap_disk_size = 1,template_id = 70)
    import pdb;pdb.set_trace()
    g.delete_vm(vm)
