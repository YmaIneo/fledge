# -*- coding: utf-8 -*-

# FLEDGE_BEGIN
# See: http://fledge-iot.readthedocs.io/
# FLEDGE_END

""" Provides utility functions to build a Fledge Support bundle.
"""
import datetime
import os
from os.path import basename
import glob
import sys
import shutil
import json
import tarfile
import fnmatch
import subprocess

from fledge.common import utils
from fledge.common.common import _FLEDGE_ROOT, _FLEDGE_DATA
from fledge.common.configuration_manager import ConfigurationManager
from fledge.common.logger import FLCoreLogger
from fledge.common.plugin_discovery import PluginDiscovery
from fledge.common.storage_client import payload_builder
from fledge.services.core.api.python_packages import get_packages_installed
from fledge.services.core.api.service import get_service_records, get_service_installed
from fledge.services.core.connect import *


__author__ = "Amarendra K Sinha"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"

_LOGGER = FLCoreLogger().get_logger(__name__)

_NO_OF_FILES_TO_RETAIN = 3
_SYSLOG_FILE = '/var/log/messages' if utils.is_redhat_based() else '/var/log/syslog'
_PATH = _FLEDGE_DATA if _FLEDGE_DATA else _FLEDGE_ROOT + '/data'


class SupportBuilder:

    _out_file_path = None
    _interim_file_path = None
    _storage = None

    def __init__(self, support_dir):
        try:
            if not os.path.exists(support_dir):
                os.makedirs(support_dir)
            else:
                self.check_and_delete_bundles(support_dir)

            self._out_file_path = support_dir
            self._interim_file_path = support_dir
            self._storage = get_storage_async()  # from fledge.services.core.connect
        except (OSError, Exception) as ex:
            _LOGGER.error(ex, "Error in initializing SupportBuilder class.")
            raise RuntimeError(str(ex))

    async def build(self):
        try:
            today = datetime.datetime.now()
            file_spec = today.strftime('%y%m%d-%H-%M-%S')
            tar_file_name = self._out_file_path+"/"+"support-{}.tar.gz".format(file_spec)
            pyz = tarfile.open(tar_file_name, "w:gz")
            try:
                await self.add_fledge_version_and_schema(pyz)
                self.add_syslog_fledge(pyz, file_spec)
                self.add_syslog_storage(pyz, file_spec)
                self.add_syslog_utility(pyz)
                cf_mgr = ConfigurationManager(self._storage)
                try:
                    south_cat = await cf_mgr.get_category_child("South")
                    south_categories = [sc["key"] for sc in south_cat]
                    for service in south_categories:
                        self.add_syslog_service(pyz, file_spec, service)
                except:
                    pass
                try:
                    north_cat = await cf_mgr.get_category_child("North")
                    north_categories = [nc["key"] for nc in north_cat]
                    for task in north_categories:
                        if task != "OMF_TYPES":
                            self.add_syslog_service(pyz, file_spec, task)
                except:
                    pass
                await self.add_table_configuration(pyz, file_spec)
                await self.add_table_audit_log(pyz, file_spec)
                await self.add_table_schedules(pyz, file_spec)
                await self.add_table_scheduled_processes(pyz, file_spec)
                await self.add_table_statistics_history(pyz, file_spec)
                await self.add_table_plugin_data(pyz, file_spec)
                await self.add_table_streams(pyz, file_spec)
                self.add_service_registry(pyz, file_spec)
                self.add_machine_resources(pyz, file_spec)
                self.add_psinfo(pyz, file_spec)
                self.add_script_dir_content(pyz)
                self.add_package_log_dir_content(pyz)
                self.add_software_list(pyz, file_spec)
                self.add_python_packages_list(pyz, file_spec)
            finally:
                pyz.close()
        except Exception as ex:
            _LOGGER.error(ex, "Error in creating Support .tar.gz file.")
            raise RuntimeError(str(ex))

        self.check_and_delete_temp_files(self._interim_file_path)
        _LOGGER.info("Support bundle %s successfully created.", tar_file_name)
        return tar_file_name

    def check_and_delete_bundles(self, support_dir):
        files = glob.glob(support_dir + "/" + "support*.tar.gz")
        files.sort(key=os.path.getmtime)
        if len(files) >= _NO_OF_FILES_TO_RETAIN:
            for f in files[:-2]:
                if os.path.isfile(f):
                    os.remove(os.path.join(support_dir, f))

    def check_and_delete_temp_files(self, support_dir):
        # Delete all non *.tar.gz files
        for f in os.listdir(support_dir):
            if not fnmatch.fnmatch(f, 'support*.tar.gz'):
                os.remove(os.path.join(support_dir, f))

    def write_to_tar(self, pyz, temp_file, data):
        with open(temp_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)
        pyz.add(temp_file, arcname=basename(temp_file))

    async def add_fledge_version_and_schema(self, pyz):
        temp_file = self._interim_file_path + "/" + "fledge-info"
        with open('{}/VERSION'.format(_FLEDGE_ROOT)) as f:
            lines = [line.rstrip() for line in f]
        self.write_to_tar(pyz, temp_file, lines)

    def add_syslog_fledge(self, pyz, file_spec):
        # The fledge entries from the syslog file
        temp_file = self._interim_file_path + "/" + "syslog-{}".format(file_spec)
        try:
            subprocess.call("grep -a '{}' {} > {}".format("Fledge", _SYSLOG_FILE, temp_file), shell=True)
        except OSError as ex:
            raise RuntimeError("Error in creating {}. Error-{}".format(temp_file, str(ex)))
        pyz.add(temp_file, arcname='logs/sys/{}'.format(basename(temp_file)))

    def add_syslog_storage(self, pyz, file_spec):
        # The contents of the syslog file that relate to the database layer (postgres)
        temp_file = self._interim_file_path + "/" + "syslogStorage-{}".format(file_spec)
        try:
            subprocess.call("grep -a '{}' {} > {}".format("Fledge Storage", _SYSLOG_FILE, temp_file), shell=True)
        except OSError as ex:
            raise RuntimeError("Error in creating {}. Error-{}".format(temp_file, str(ex)))
        pyz.add(temp_file, arcname='logs/sys/{}'.format(basename(temp_file)))

    def add_syslog_service(self, pyz, file_spec, service):
        # The fledge entries from the syslog file for a service or task
        # Replace space occurrences with hyphen for service or task - so that file is created
        tmp_svc = service.replace(' ', '-')
        temp_file = self._interim_file_path + "/" + "syslog-{}-{}".format(tmp_svc, file_spec)
        try:
            subprocess.call("grep -a -E '(Fledge {})\[' {} > {}".format(service, _SYSLOG_FILE, temp_file), shell=True)
            pyz.add(temp_file, arcname='logs/sys/{}'.format(basename(temp_file)))
        except Exception as ex:
            raise RuntimeError("Error in creating {}. Error-{}".format(temp_file, str(ex)))

    def add_syslog_utility(self, pyz):
        # syslog utility files
        for filename in os.listdir("/tmp"):
            if filename.startswith("fl_syslog"):
                temp_file = "/tmp/{}".format(filename)
                pyz.add(temp_file, arcname='logs/sys/{}'.format(filename))

    async def add_table_configuration(self, pyz, file_spec):
        # The contents of the configuration table from the storage layer
        temp_file = self._interim_file_path + "/" + "configuration-{}".format(file_spec)
        data = await self._storage.query_tbl("configuration")
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_audit_log(self, pyz, file_spec):
        # The contents of the audit log from the storage layer
        temp_file = self._interim_file_path + "/" + "audit-{}".format(file_spec)
        data = await self._storage.query_tbl("log")
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_schedules(self, pyz, file_spec):
        # The contents of the schedules table from the storage layer
        temp_file = self._interim_file_path + "/" + "schedules-{}".format(file_spec)
        data = await self._storage.query_tbl("schedules")
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_scheduled_processes(self, pyz, file_spec):
        temp_file = self._interim_file_path + "/" + "scheduled_processes-{}".format(file_spec)
        data = await self._storage.query_tbl("scheduled_processes")
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_statistics_history(self, pyz, file_spec):
        # The contents of the statistics history from the storage layer
        temp_file = self._interim_file_path + "/" + "statistics-history-{}".format(file_spec)
        payload = payload_builder.PayloadBuilder() \
            .LIMIT(1000) \
            .ORDER_BY(['history_ts', 'DESC']) \
            .payload()
        data = await self._storage.query_tbl_with_payload("statistics_history", payload)
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_plugin_data(self, pyz, file_spec):
        # The contents of the plugin_data from the storage layer
        temp_file = self._interim_file_path + "/" + "plugin-data-{}".format(file_spec)
        payload = payload_builder.PayloadBuilder() \
            .LIMIT(1000) \
            .ORDER_BY(['key', 'ASC']) \
            .payload()
        data = await self._storage.query_tbl_with_payload("plugin_data", payload)
        self.write_to_tar(pyz, temp_file, data)

    async def add_table_streams(self, pyz, file_spec):
        # The contents of the streams from the storage layer
        temp_file = self._interim_file_path + "/" + "streams-{}".format(file_spec)
        payload = payload_builder.PayloadBuilder() \
            .LIMIT(1000) \
            .ORDER_BY(['id', 'ASC']) \
            .payload()
        data = await self._storage.query_tbl_with_payload("streams", payload)
        self.write_to_tar(pyz, temp_file, data)

    def add_service_registry(self, pyz, file_spec):
        # The contents of the service registry
        temp_file = self._interim_file_path + "/" + "service_registry-{}".format(file_spec)
        data = {
            "about": "Service Registry",
            "serviceRegistry": get_service_records()
        }
        self.write_to_tar(pyz, temp_file, data)

    def add_machine_resources(self, pyz, file_spec):
        def _execute_command(cmd):
            sub = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).stdout.readlines()
            convert_bytes_to_string = [s.decode() for s in sub]
            remove_whitespaces_from_list = [bts.strip().replace(' ', '') for bts in convert_bytes_to_string]
            result = {}
            for rw in remove_whitespaces_from_list:
                kv = rw.split(":")
                result[kv[0]] = kv[1]
            return result

        # Details of machine resources, memory size, amount of available memory, storage size and amount of free storage
        temp_file = self._interim_file_path + "/" + "machine-{}".format(file_spec)
        total, used, free = shutil.disk_usage("/")
        memory = subprocess.Popen('free -h', shell=True, stdout=subprocess.PIPE).stdout.readlines()[1].split()[1:]
        hostname_info = _execute_command('hostnamectl status')
        cpu_architecture_info = _execute_command('lscpu')
        data = {
            "about": "Machine resources",
            "platform": sys.platform,
            "totalMemory": memory[0].decode(),
            "usedMemory": memory[1].decode(),
            "freeMemory": memory[2].decode(),
            "totalDiskSpace_MB": int(total / (1024 * 1024)),
            "usedDiskSpace_MB": int(used / (1024 * 1024)),
            "freeDiskSpace_MB": int(free / (1024 * 1024)),
            "hostnameInfo": hostname_info,
            "cpuArchitectureInfo": cpu_architecture_info
        }
        self.write_to_tar(pyz, temp_file, data)

    def add_psinfo(self, pyz, file_spec):
        # A PS listing of al the python applications running on the machine
        temp_file = self._interim_file_path + "/" + "psinfo-{}".format(file_spec)
        a = subprocess.Popen('ps -aufx | egrep "(%MEM|fledge\.)" | grep -v grep', shell=True,
                             stdout=subprocess.PIPE).stdout.readlines()
        c = [b.decode() for b in a]  # Since "a" contains return value in bytes, convert it to string

        c_tasks = subprocess.Popen('ps -aufx | grep "./tasks" | grep -v grep', shell=True,
                                   stdout=subprocess.PIPE).stdout.readlines()
        c_tasks_decode = [t.decode() for t in c_tasks]
        if c_tasks_decode:
            c.extend(c_tasks_decode)
        # Remove "/n" from the c list output
        data = {
            "runningProcesses": list(map(str.strip, c))
        }
        self.write_to_tar(pyz, temp_file, data)

    def add_script_dir_content(self, pyz):
        script_file_path = _PATH + '/scripts'
        if os.path.exists(script_file_path):
            # recursively 'true' by default and __pycache__ dir excluded
            pyz.add(script_file_path, arcname='scripts', filter=self.exclude_pycache)

    def add_package_log_dir_content(self, pyz):
        script_package_logs_path = _PATH + '/logs'
        if os.path.exists(script_package_logs_path):
            # recursively 'true' by default and __pycache__ dir excluded
            pyz.add(script_package_logs_path, arcname='logs/package', filter=self.exclude_pycache)

    def add_software_list(self, pyz, file_spec) -> None:
        data = {
            "plugins": PluginDiscovery.get_plugins_installed(),
            "services": get_service_installed()
        }
        temp_file = self._interim_file_path + "/" + "software-{}".format(file_spec)
        self.write_to_tar(pyz, temp_file, data)

    def add_python_packages_list(self, pyz, file_spec) -> None:
        data = {'packages': get_packages_installed()}
        temp_file = self._interim_file_path + "/" + "python-packages-{}".format(file_spec)
        self.write_to_tar(pyz, temp_file, data)

    def exclude_pycache(self, tar_info):
        return None if '__pycache__' in tar_info.name else tar_info
