import os
import shutil
import ftplib
import zipfile
import time
import socket
import hashlib
from datetime import datetime as dt
import json
import dataset
import settings as s


class Downloader:
    """
    To construct an object of this class you need to use next parameters:

    url: url of ftp-server with data

    login: in the format ('user', 'password')

    downloaded_dirs: directories with file s for downloading. Must have list
                    type. If he given list is empty, then all directories are
                    processed and all files in these are downloaded.

    config: a config file. It must have a dict type.

    store_archives: by default False. If flag is True, the program store
    a zip archive to '%path_to_your_storage/extract_directory' where
    extract_directiry is a directory where the zip archive has been unpacked.
    """

    def __init__(self, url: str, login: dict, config: dict,
                 downloaded_dirs: list, store_archives=False):
        self.url = url
        self.login = login
        self.tickets = list()
        self.ftp = None
        self.table = None
        self.config = config
        self.downloaded_dirs = downloaded_dirs
        self.store_zip = store_archives
        self.file_report = {
            'downloaded': 0,
            'unpacked': 0,
            'registered': 0
        }

        self.retry_count = 0

    def check_config(self) -> dict:
        report = {
            'status': 'fail',
            'method': 'check_config',
            'reason': 'unknown exception',
        }
        if not isinstance(self.config, dict):
            report['reason'] = 'config has not dict type. Actually is %s' % \
                               type(self.config)
        try:
            # check an ip
            if not isinstance(self.config['DB_HOST'], str):
                report['reason'] = 'a database host isn\'t str-type. Actually'\
                                   ' it\'s %s' % type(self.config['DB_HOST'])
                return report
            elif len(self.config['DB_HOST'].split('.')) != 4:
                report['reason'] = 'an incorrect IP adress of DB: %s' \
                                   % self.config['DB_HOST']
                return report

            # check a port
            if not isinstance(self.config['DB_PORT'], int):
                report['reason'] = 'a database port isn\'t int-type. Actually'\
                                   ' it\'s %s' % type(self.config['DB_PORT'])
                return report
            elif len(str(self.config['DB_PORT'])) not in [1, 2, 3, 4, 5]:
                report['reason'] = 'an incorrect port: %s' \
                                   % self.config['DB_PORT']
                return report

            # check an user
            if not self.config['DB_NAME']:
                report['reason'] = 'an empty database name'
                return report
            elif not isinstance(self.config['DB_NAME'], str):
                report['reason'] = 'a database name isn\'t str-type. Actually'\
                                   ' it\'s %s' % type(self.config['DB_NAME'])
                return report

            # check an user
            if not self.config['DB_USER']:
                report['reason'] = 'an empty database user'
                return report
            elif not isinstance(self.config['DB_USER'], str):
                report['reason'] = 'a database user isn\'t str-type. Actually'\
                                   ' it\'s %s' % type(self.config['DB_USER'])
                return report

            # check a password
            if not self.config['DB_PASSWORD']:
                report['reason'] = 'an empty database password'
                return report
            elif not isinstance(self.config['DB_PASSWORD'], str):
                report['reason'] = 'a database password isn\'t str-type.' \
                                   ' Actually it\'s %s' \
                                   % type(self.config['DB_PASSWORD'])
                return report

            # check a table name
            if not self.config['DB_TABLE_NAME']:
                report['reason'] = 'an empty table name'
                return report
            elif not isinstance(self.config['DB_TABLE_NAME'], str):
                report['reason'] = 'a table name isn\'t str-type. Actually' \
                                   ' it\'s %s' \
                                   % type(self.config['DB_TABLE_NAME'])
                return report

            # check a source name
            if not self.config['SOURCE_NAME']:
                report['reason'] = 'an empty source name'
                return report
            elif not isinstance(self.config['SOURCE_NAME'], str):
                report['reason'] = 'a source name  isn\'t str-type. ' \
                                   'Actually it\'s %s' \
                                   % type(self.config['SOURCE_NAME'])
                return report

            # check a storage path
            if not self.config['STORAGE_PATH']:
                report['reason'] = 'an empty storage path'
                return report
            elif not isinstance(self.config['STORAGE_PATH'], str):
                report['reason'] = 'a storage path isn\'t str-type. ' \
                                   'Actually it\'s %s' \
                                   % type(self.config['STORAGE_PATH'])
                return report

            # check a temporary storage path
            if not self.config['TMP_STORAGE_PATH']:
                report['reason'] = 'an empty storage path'
                return report
            elif not isinstance(self.config['TMP_STORAGE_PATH'], str):
                report['reason'] = 'a temporary storage path isn\'t str-type.'\
                                   ' Actually it\'s %s' \
                                   % type(self.config['TMP_STORAGE_PATH'])
                return report
        except KeyError as e:
            report['reason'] = 'config has no field %s' % (e.args[0])
            return report
        report['reason'] = 'success'
        report['status'] = 'ok'
        return report

    def create_connection_string(self) -> str:
        connection_string = "postgresql://%s:%s@%s:%s/%s" % (
            self.config['DB_USER'],
            self.config['DB_PASSWORD'],
            self.config['DB_HOST'],
            self.config['DB_PORT'],
            self.config['DB_NAME']
        )
        return connection_string

    def create_ftp_connection(self) -> dict:
        report = {
            'status': 'fail',
            'method': 'create_ftp_connection',
            'reason': 'unknown exception',
        }
        try:
            ftp = ftplib.FTP(self.url, timeout=5.0)
        except:
            report['reason'] = 'cannot connect to a server'
            return report
        try:
            ftp.login(self.login['username'], self.login['password'])
        except:
            report['reason'] = 'cannot login to a server'
            return report
        report['reason'] = ''
        report['status'] = 'ok'
        self.ftp = ftp
        return report

    def retry_connect(self) -> str:
        status = 'fail'
        count = 0
        try:
            self.ftp.quit()
        except:
            pass

        while count < 5:
            try:
                self.ftp = ftplib.FTP(self.url, timeout=5.0)
                self.ftp.login(self.login['username'], self.login['password'])
                status = 'ok'
                break
            except:
                time.sleep(10)
                count += 1
                continue
        return status

    def set_table(self, table_name: str) -> dict:
        """
        This method tries to return a table from a database. If no table in
        the database, this one will be created.
        :return:
        """
        report = {
            'status': 'fail',
            'method': 'set_table',
            'reason': 'unknown exception',
        }

        connection_string = self.create_connection_string()
        try:
            db = dataset.connect(connection_string)
        except:
            report['reason'] = 'db connection fail'
            return report

        if self.config['DB_TABLE_NAME'] not in db.tables:
            table = self.create_new_table(table_name, db)
            if table is None:
                report['reason'] = 'cannot create a new table with name %s' % \
                                   table_name
                return report
            report['reason'] = ''
            report['status'] = 'ok'
            self.table = table
            return report
        else:
            try:
                table = db.get_table(table_name)
            except:
                report['reason'] = 'cannot get the table "%s" from the ' \
                                   'database' % table_name
                return report
            report['reason'] = ''
            report['status'] = 'ok'
            self.table = table
            return report

    def create_new_table(self, table_name: str, db):
        """
        This method creates a table with a given name in a database
        :param table_name: a name of a created table
        :return: the created table
        """
        try:
            table = db.create_table(table_name)
        except:
            return None
        try:
            table.create_column('meta_source', db.types.text)
            table.create_column('meta_version', db.types.text)
            table.create_column('meta_storage_id', db.types.text)
            table.create_column('meta_storage', db.types.text)
            table.create_column('meta_format', db.types.text)
            table.create_column('meta_provider', db.types.text)
            table.create_column('meta_created_at', db.types.datetime)
            table.create_column('meta_updated_at', db.types.datetime)
            table.create_column('meta_status', db.types.text)
            table.create_column('meta_resource_id', db.types.text)
            table.create_column('meta_check_sum', db.types.text)
        except:
            return None
        return table

    def create_storage(self, path: str) -> dict:
        """
        The method tries to get storage to store new data.
        :return: a status 'ok' if the storage has been created and 'fail'
                    otherwise.
        """
        report = {
            'status': 'fail',
            'method': 'create_storage',
            'reason': 'unknown exception',
        }
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError:
                report['reason'] = 'cannot create a new directory in %s' % path
                return report
        elif os.path.isfile(path):
            report['reason'] = 'a path %s is a file so cannot create ' \
                               'a storage' % path
            return report
        elif os.path.isdir(path):
            report['reason'] = ''
            report['status'] = 'ok'
            return report
        else:
            return report
        report['reason'] = ''
        report['status'] = 'ok'
        return report

    def create_tmp_storage(self, path: str) -> dict:
        """
        This method creates temporary storage for downloaded zip archives.
        If one has been created before it is just removed and created again.
        :return:
        """
        report = {
            'status': 'fail',
            'method': 'create_tmp_storage',
            'reason': 'unknown exception'
        }
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError:
                report['reason'] = 'cannot create a new directory for ' \
                                'temporary storage in %s' \
                                % path
                return report
        report['reason'] = ''
        report['status'] = 'ok'
        return report

    def join_path(self, head: str, tail: str) -> str:
        """
        This method joins paths.
        :param head:
        :param tail:
        :return: a path of string type
        """
        if head == '/':
            return '/%s' % tail
        else:
            return "%s/%s" % (head, tail)

    def cwd(self, path: str):
        status = 'fail'
        count = 0
        while count < 2:
            try:
                self.ftp.cwd(path)
            except ftplib.all_errors as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return status
                else:
                    count += 1
                    continue
            except socket.timeout as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return status
                else:
                    count += 1
                    continue
            except Exception as e:
                return status
            break

        status = 'ok'
        return status

    def walk(self, path: str) -> tuple:
        """
        This method walks the path and return 3 parameters: a root path, direc-
        tories and files in the path.
        :param path: a path to walk
        :return: root, dirs, files
        """
        items = list()
        files = list()
        dirs = list()

        root = path

        count = 0
        while count < 2:
            status = self.cwd(root)
            if status != 'ok':
                return root, [], []

            try:
                self.ftp.dir(items.append)
            except ftplib.all_errors as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return root, [], []
                else:
                    count += 1
                    continue
            except socket.timeout as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return root, [], []
                else:
                    count += 1
                    continue
            except Exception as e:
                return root, [], []
            break

        for i, item in enumerate(items):
            item = item.split()[-1]

            if self.is_dir(self.join_path(root, item)):
                dirs.append(item)
            else:
                files.append(item)

        return root, dirs, files

    def get_check_sum(self, path: str) -> str:
        blocksize = 65536
        hasher = hashlib.md5()
        with open(path, 'rb') as afile:
            try:
                buf = afile.read(blocksize)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = afile.read(blocksize)
            except:
                return ''
        hash = hasher.hexdigest()
        return hash

    def fetch_file(self, path_to_file) -> dict:
        """
        This method downloads a zip-file to storage. If a file was been
        downloaded before, it is not downloaded
        :param path_to_file: a filename of form 'any_filename.xml.zip'
        :return: a special report
        """
        report = {
            'status': 'fail',
            'downloaded': 'no',
            'unpacked': 'no',
            'registered': 'no'
        }
        filename = path_to_file.split('/')[-1]
        if self.exist_in_database(filename):
            report['status'] = 'ok'
            return report
        else:
            download_status = self.download_file(path_to_file)
            if download_status == 'ok':
                report['downloaded'] = 'yes'

                path_to_zip = os.path.join(self.config['TMP_STORAGE_PATH'],
                                           filename)
                check_sum = self.get_check_sum(path_to_zip)
                if not check_sum:
                    return report

                unpacked_status = self.unpack_file(filename)
                if unpacked_status != 'ok':
                    return report
                else:
                    report['unpacked'] = 'yes'
                    file_status = 'fetched'
                    register_data_status = self.register_data(
                        filename,
                        filename,
                        1,
                        file_status,
                        check_sum
                    )
                    if register_data_status == 'ok':
                        report['status'] = 'ok'
                        report['registered'] = 'yes'
            return report

    def register_data(self, resource_id: str, storage_id: str, version: int,
                      file_status: str, check_sum) -> str:
        status = 'fail'
        now_timestamp = dt.utcnow()
        data = {
            'meta_source': self.config['SOURCE_NAME'],
            'meta_version': version,
            'meta_storage_id': storage_id,
            'meta_storage': 'filesystem',
            'meta_format': 'zip',
            'meta_provider': 'downloader.py',
            'meta_created_at': now_timestamp,
            'meta_updated_at': now_timestamp,
            'meta_status': file_status,
            'meta_resource_id': resource_id,
            'meta_check_sum': check_sum
        }
        result = self.table.insert(data)
        if result:
            status = 'ok'
        return status

    def exist_in_database(self, filename: str) -> bool:
        try:
            result = list(self.table.find(meta_resource_id=filename))
            if bool(result):
                return True
            return False
        except:
            return False

    def is_dir(self, path: str) -> bool:
        """
        The method checks if a given path is a directory.
        :param path: a path to check
        :return: True if a given path is a dir and False otherwise
        """
        try:
            self.ftp.cwd(path)
            self.ftp.cwd('..')
            return True
        except Exception as e:
            return False

    def is_dir_to_download(self, path: str) -> bool:
        if len(self.downloaded_dirs) == 0:
            return True

        for dir in self.downloaded_dirs:
            if dir in path:
                return True
        return False

    def download_file(self, path: str) -> str:
        """
        The method just downloads a zip file to a directory
        '%your_storage_path%/zip_files'.
        :param path: a path to file for downloading
        :return: None
        """
        status = 'fail'
        filename = str(path).split("/")[-1]
        zip_file_path = os.path.join(self.config['TMP_STORAGE_PATH'], filename)

        count = 0
        while count < 2:
            try:
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path)

                zip_file = open(zip_file_path, "wb")
                self.ftp.retrbinary("RETR " + path, zip_file.write)
                zip_file.close()
            except ftplib.all_errors as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return status
                else:
                    count += 1
                    continue
            except socket.timeout as e:
                status = self.retry_connect()
                if status != 'ok':
                    self.retry_count += 1
                    return status
                else:
                    count += 1
                    continue
            except Exception as e:
                return status
            break
        status = 'ok'
        return status

    def unpack_file(self, filename: str) -> str:
        """
        This method tries to unpack file to a directory
        '%your_storage_path%/unzip_files/stripped_filename' where
        stripped_filename is the name without .xml.zip because filename has
        the format 'any_filename.xml.zip'
        :param filename: in the format '.zip'
        :return: a status 'ok' if the file has been unpacked and 'fail'
            otherwise.
        """
        status = 'fail'
        if not filename.endswith('.zip'):
            return status

        dir_name = filename[:-8]  # strip the zip format in filename
        uncompressed_file_path = os.path.join(self.config['TMP_STORAGE_PATH'],
                                              dir_name)
        try:
            os.makedirs(uncompressed_file_path)
        except OSError:
            try:
                shutil.rmtree(uncompressed_file_path)
                os.makedirs(uncompressed_file_path)
            except:
                return status

        try:
            compressed_file_path = os.path.join(
                self.config['TMP_STORAGE_PATH'], filename)
            z_file = zipfile.ZipFile(compressed_file_path, 'r')
            z_file.extractall(uncompressed_file_path)

            if self.store_zip:
                old_zip_path = \
                    os.path.join(self.config['STORAGE_PATH'], filename)
                if os.path.exists(old_zip_path):
                    os.remove(old_zip_path)
                shutil.move(compressed_file_path, self.config['STORAGE_PATH'])
        except:
            try:
                shutil.rmtree(os.path.join(uncompressed_file_path, dir_name))
            except:
                return status
            return status

        z_file.close()
        status = 'ok'
        return status

    def write_log(self, report: dict) -> dict:
        log = {
            'status': report['status'],
            'method': report['method'],
            'reason': report['reason'],
            'downloaded': self.file_report['downloaded'],
            'unpacked': self.file_report['unpacked'],
            'registered': self.file_report['registered'],
        }
        return log

    def process_dir(self, path: str):
        """
        Process files in a given path.
        :param path: a path to a directory or a file
        :return: None
        """
        root, dirs, files = self.walk(path)

        for filename in files:
            next_path = self.join_path(root, filename)
            if filename.endswith(".zip"):
                report = self.fetch_file(next_path)
                if report['downloaded'] == 'yes':
                    self.file_report['downloaded'] += 1
                if report['unpacked'] == 'yes':
                    self.file_report['unpacked'] += 1
                if report['registered'] == 'yes':
                    self.file_report['registered'] += 1

        for dir in dirs:
            dir_path = self.join_path(root, dir)
            self.process_dir(dir_path)

    def run(self, path_to_start='') -> dict:
        report = self.check_config()
        if report['status'] != 'ok':
            log = self.write_log(report)
            return log

        report = self.set_table(self.config['DB_TABLE_NAME'])
        if report['status'] != 'ok':
            log = self.write_log(report)
            return log

        report = self.create_storage(self.config['STORAGE_PATH'])
        if report['status'] != 'ok':
            log = self.write_log(report)
            return log

        report = self.create_tmp_storage(self.config['TMP_STORAGE_PATH'])
        if report['status'] != 'ok':
            log = self.write_log(report)
            return log

        report = self.create_ftp_connection()
        if report['status'] != 'ok':
            self.write_log(report)
            self.ftp.quit()
            log = self.write_log(report)
            return log

        if path_to_start and self.is_dir(path_to_start):
            root, regions, files = self.walk(path_to_start)

            for region in regions:
                region_path = self.join_path(path_to_start, region)

                root, dirs, files = self.walk(region_path)
                for dir in dirs:
                    path = self.join_path(region_path, dir)
                    if self.is_dir(path) and self.is_dir_to_download(path):
                        self.process_dir(path)
        report = {
            'status': 'ok',
            'method': 'run',
            'reason': 'success'
        }
        try:
            self.ftp.quit()
        except:
            pass
        log = self.write_log(report)
        return log

