#!/usr/bin/python
# encoding=utf-8
import requests, sys, os, re, time
from optparse import OptionParser
import Queue
import time
import sys
import json
import threading
import signal


class WGet:

    def __init__(self, block=1024 * 10, headers={}):
        self.block = block
        self.total = 0
        self.download_size = 0
        self.size = 0
        self.filename = ''
        self.task_queue = Queue.Queue(maxsize=100)
        self.block_index = 0
        self.next_need_to_merge_block_index = 0
        self.download_url = None
        self.headers = headers
        self.start_time = None
        self.lock = threading.Lock()
        self.file_downloading = {}
        self.finish = False

    @property
    def download_config(self):
        return "{}.config".format(self.filename)

    def load_download_config(self):
        if os.path.exists(self.download_config):
            with open(self.download_config, 'rb') as f:
                config = json.loads(f.read())
                self.next_need_to_merge_block_index = config['next_need_to_merge_block_index']
                self.file_downloading = config['file_downloading']
                self.block_index = self.next_need_to_merge_block_index
        if os.path.exists(self.filename):
            self.download_size = os.path.getsize(self.filename)

    def dump_download_config(self):
        with open(self.download_config, 'wb') as f:
            f.write(json.dumps({
                "next_need_to_merge_block_index": self.next_need_to_merge_block_index,
                "file_downloading": self.file_downloading,
            }))

    @staticmethod
    def remove_nonchars(name):
        (name, _) = re.subn(ur'[\\\/\:\*\?\"\<\>\|]', '', name)
        return name

    def support_continue(self, url):
        headers = {
                'Range': 'bytes=0-4'
                }
        try:
            r = requests.head(url, headers = headers)
            crange = r.headers['content-range']
            self.total = int(re.match(ur'^bytes 0-4/(\d+)$', crange).group(1))
            return True
        except:
            pass
        try:
            self.total = int(r.headers['content-length'])
        except:
            self.total = 0
        return False

    def boss(self):
        if self.total == 0:
            raise Exception("total size must be greater then 0 byte")

        while self.finish is False and self.block_index * self.block < self.total:
            self.task_queue.put(self.block_index, block=True)
            self.block_index += 1

    def gen_header_range_by_block_index(self, block_index):
        s1 = block_index * self.block
        s2 = (s1 + self.block - 1)
        s2 = min(self.total-1, s2)
        h_range = "bytes={}-{}".format(s1, s2)
        return h_range

    def worker(self):

        while 1 and self.finish is False:
            try:
                block_index = self.task_queue.get(block=True, timeout=0.01)
            except Queue.Empty:
                return

            self._worker(block_index)

    def _worker(self, block_index):

        file_path = "{}.{}.tmp".format(self.filename, block_index)
        if os.path.exists(file_path) and file_path not in self.file_downloading:
            pass
        else:
            headers = self.headers.copy()
            h_range = self.gen_header_range_by_block_index(block_index)
            headers['Range'] = h_range
            self.file_downloading[file_path] = 1
            f = open(file_path, 'wb')

            def callback(chunk):
                f.write(chunk)
                self.lock.acquire()
                self.size += len(chunk)
                self.lock.release()
                self.pprint()

            try:
                self._download_file(self.download_url, headers, callback)
            except:
                os.remove(file_path)
                raise
            finally:
                del self.file_downloading[file_path]
                f.close()

    def merge(self):

        with open(self.filename, 'ab') as f:

            while self.finish is False and self.next_need_to_merge_block_index * self.block < self.total:
                file_path = "{}.{}.tmp".format(self.filename, self.next_need_to_merge_block_index)
                if os.path.exists(file_path) and self.file_downloading.has_key(file_path) is False:
                    ft = open(file_path, 'rb')
                    f.write(ft.read())
                    f.flush()
                    ft.close()
                    self.next_need_to_merge_block_index += 1
                    os.remove(file_path)

                else:
                    time.sleep(0.1)

            self.finish = True

    def normal_download(self):

        f = open(self.filename, 'wb')

        def callback(chunk):
            f.write(chunk)
            self.size += len(chunk)
            self.pprint()

        try:
            self._download_file(self.download_url, self.headers, callback)
        except:
            raise
        finally:
            f.close()
        print "\nDownload Finish"

    @staticmethod
    def _download_file(url, headers={}, callback=None):
        r = requests.get(url, stream=True, headers=headers)
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                if callback is not None:
                    callback(chunk)

    def determine_thread_num(self):

        t = (self.total - self.download_size) / self.block - self.block_index
        if t <= 5:
            return 1
        elif t <= 20:
            return 3
        else:
            return 5

    def multi_thread_download(self):

        workers = [threading.Thread(target=self.worker) for i in range(self.determine_thread_num())]
        boss = threading.Thread(target=self.boss)
        merge = threading.Thread(target=self.merge)
        print "[+] 线程数量：{}".format(len(workers))
        boss.start()
        merge.start()
        for item in workers:
            item.start()
        while self.finish is False:
            time.sleep(0.1)
        print "\nDownload Finish"

    def pprint(self):
        now = self.size + self.download_size
        if self.total == 0:
            p = None
        else:
            p = round(float(now)/self.total, 1) * 100
        spend = time.time() - self.start_time
        speed = round((float(self.size) / 1024 / spend),2)
        sys.stdout.write('\rNow: {}, Total: {}, {}% | Time: {}s,  '
                         'Speed: {}k/s  '.format(now, self.total,p, round(spend,2), speed))
        sys.stdout.flush()

    def p_size(self):
        if self.total > 0:
            print "[+] Size: %dKB" % (self.total / 1024)
        else:
            print "[+] Size: None"

    def download(self, url, filename=None):
        self.start_time = time.time()
        self.download_url = url
        if filename is None:
            self.filename = self.remove_nonchars(url)
        else:
            self.filename = filename

        if os.path.exists(self.filename) and os.path.exists(self.download_config) is False:
            raise Exception("exists {}".format(self.filename))

        if self.support_continue(url):  # 支持断点续传
            print "[+] 多线程下载..."
            self.p_size()
            self.load_download_config()
            try:
                self.multi_thread_download()
                if os.path.exists(self.download_config):
                    os.remove(self.download_config)
            except:
                self.dump_download_config()
                raise
        else:
            print "[+] 普通下载..."
            self.p_size()
            self.normal_download()

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-u", "--url", dest="url",  
            help="target url")
    parser.add_option("-o", "--output", dest="filename",  
            help="download file to save")
    parser.add_option("-a", "--user-agent", dest="useragent", 
            help="request user agent", default='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 \
                    (KHTML, like Gecko) Chrome/40.0.2214.111 Safari/537.36')
    parser.add_option("-r", "--referer", dest="referer", 
            help="request referer")
    parser.add_option("-c", "--cookie", dest="cookie", 
            help="request cookie", default = 'foo=1;')
    (options, args) = parser.parse_args()
    if not options.url:
        print 'Missing url'
        sys.exit()
    if not options.filename:
        options.filename = options.url.split('/')[-1]
    headers = {
            'User-Agent': options.useragent,
            'Referer': options.referer if options.referer else options.url,
            'Cookie': options.cookie
            }
    wget = WGet(headers=headers)
    def bye(s, frame):
        print("\nDownload Pause...")
        wget.dump_download_config()
        wget.finish = True
        sys.exit(0)

    signal.signal(signal.SIGINT, bye)
    wget.download(options.url, options.filename)
