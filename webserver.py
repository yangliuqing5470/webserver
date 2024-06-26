import os
import logging
import select
import socket
import signal
import struct
import time
import epoll.epoll as epoll
import database.database as database
import timer.lst_timer as lst_timer
import threadpool.threadpool as threadpool
import httpconnect.http_connect as http_connect

MAX_FD = 65536
MAX_EVENT_NUMBER = 10000
TIMESLOT = 5

class WebServer():
    def __init__(self, args: dict):
        # 获取root文件夹路径
        self.m_root = os.path.join(os.getcwd(), "root")
        self.m_port = args["port"]
        self.m_thread_num = args["thread_num"]
        self.m_opt_linger = args["opt_linger"]
        self.m_trigmode = args["trigmode"]
        self.m_actormodel = args["actormodel"]
        # 定时器是否超时
        self.m_timeout = False
        # 是否停服
        self.m_stop_server = False
        self._init_users_and_users_timer()

    def _init_users_and_users_timer(self):
        self.users = []
        self.users_timer = []
        for _ in range(MAX_FD):
            self.users.append(http_connect.HttpConnect())
            self.users_timer.append(lst_timer.UserData())

    def _socket_to_fd(self, socket):
        """获取socket对象的文件描述符.

        """
        if isinstance(socket, int):
            fd = socket
        else:
            try:
                fd = int(socket.fileno())
            except (AttributeError, TypeError, ValueError):
                raise ValueError("Invalid file object: {!r}".format(socket)) from None
        if fd < 0:
            raise ValueError("Invalid file descriptor: {}".format(fd))
        return fd

    def _callback(self, future):
        thread_result = future.result()
        if thread_result is None:
            return
        res, socket, util_timer = thread_result
        if res == 1:
            self.adjust_timer(util_timer)
        else:
            self.deal_timer(util_timer, socket)

    def trig_mode(self):
        if self.m_trigmode == 0:
            self.m_listentrigmode = 0
            self.m_conntrigmode = 0
        elif self.m_trigmode == 1:
            self.m_listentrigmode = 0
            self.m_conntrigmode = 1
        elif self.m_trigmode == 2:
            self.m_listentrigmode = 1
            self.m_conntrigmode = 0
        elif self.m_trigmode == 3:
            self.m_listentrigmode = 1
            self.m_conntrigmode = 1

    def thread_pool(self):
        self.m_thread_pool = threadpool.ThreadPool(self.m_actormodel, self.m_thread_num)

    def sql_pool(self):
        self.m_database = database.DataBase(os.path.join(os.getcwd(), "database"))
        http_connect.HttpConnect.m_database = self.m_database  # type: ignore

    def event_listen(self):
        self.m_listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.m_opt_linger != 0:
            # 设置优雅关闭连接
            self.m_listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 1))
        else:
            self.m_listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 0, 1))
        self.m_listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.m_listen_socket.bind(("0.0.0.0", self.m_port))
        self.m_listen_socket.listen(5)
        self.m_epollfd = epoll.MyEpollSelector()
        lst_timer.Utils.m_epollfd = self.m_epollfd  # type: ignore
        utils = lst_timer.Utils(TIMESLOT)
        utils.addfd(self.m_epollfd, self.m_listen_socket, False, self.m_listentrigmode)
        http_connect.HttpConnect.m_epollfd = self.m_epollfd  # type: ignore
        # m_pipefd_0：读端; m_pipefd_1: 写端
        m_pipefd_0, m_pipefd_1 = socket.socketpair()
        m_pipefd_1.setblocking(False)
        utils.m_pipefd_write = m_pipefd_1  # type: ignore
        utils.addfd(self.m_epollfd, m_pipefd_0, False, 0)
        utils.addsig(signal.SIGPIPE, signal.SIG_IGN)
        utils.addsig(signal.SIGALRM, utils.sig_handler)
        utils.addsig(signal.SIGTERM, utils.sig_handler)
        utils.addsig(signal.SIGINT, utils.sig_handler)
        signal.alarm(TIMESLOT)
        self.utils = utils
        self.m_pipefd_0 = m_pipefd_0
        logging.info("Create listen socket {0} pipe read socket {1} and pipe write socket {2}".format(self.m_listen_socket, m_pipefd_0, m_pipefd_1))

    def timer(self, client_socket, client_address):
        fd = self._socket_to_fd(client_socket)
        self.users[fd].init(client_socket, self.m_trigmode, self.m_root)
        self.users_timer[fd].address = client_address
        self.users_timer[fd].socket = client_socket
        timer_node = lst_timer.UtilTimer(user_data=self.users_timer[fd], cb_func=lst_timer.cb_func)
        cur = time.time()
        timer_node.expire = cur + 3 * TIMESLOT      # type: ignore
        self.users_timer[fd].utiltimer = timer_node  # type: ignore
        self.utils.m_sorted_timer_list.add_timer(timer_node)

    def adjust_timer(self, timer):
        """如果在过期时间内有数据，则将定时器值往后延3个单位，并调整有序定时器链表.

        """
        cur = time.time()
        timer.expire = cur + 3 * TIMESLOT
        self.utils.m_sorted_timer_list.adjust_timer(timer)

    def deal_timer(self, timer, socket):
        fd = self._socket_to_fd(socket)
        timer.cb_func(self.m_epollfd, self.users_timer[fd])
        self.utils.m_sorted_timer_list.del_timer(timer)

    def deal_client_data(self):
        """处理新的客户端连接事件.
        
        """
        if self.m_listentrigmode == 0:
            # LT mode
            client_socket, client_address = self.m_listen_socket.accept()
            if http_connect.HttpConnect.m_user_count >= MAX_FD:
                self.utils.show_error(client_socket, "Internal server busy")
                return False
            self.timer(client_socket, client_address)
            logging.info("Get new client {0} and current client number {1}".format(client_socket, http_connect.HttpConnect.m_user_count))
        else:
            # ET mode
            while True:
                try:
                    client_socket, client_address = self.m_listen_socket.accept()
                except socket.error:
                    break
                if http_connect.HttpConnect.m_user_count >= MAX_FD:
                    self.utils.show_error(client_socket, "Internal server busy")
                    break
                self.timer(client_socket, client_address)
                logging.info("Get new client {0} and current client number {1}".format(client_socket, http_connect.HttpConnect.m_user_count))
            return False
        return True

    def deal_signal(self):
        chunk = self.m_pipefd_0.recv(1024)
        if not chunk:
            return False
        signal_value = int(chunk.decode())
        logging.info("Deal with signal {0}".format(self.utils.signal_docstring_map.get(signal_value, signal_value)))
        if signal_value == signal.SIGALRM.value:
            self.m_timeout = True
        elif signal_value == signal.SIGTERM.value or signal_value == signal.SIGINT.value:
            self.m_stop_server = True
        return True

    def deal_read(self, socket):
        socketfd = self._socket_to_fd(socket)
        util_timer = self.users_timer[socketfd].utiltimer
        result = (socket, util_timer)
        if self.m_actormodel == 1:
            # reactor
            self.m_thread_pool.append(self.users[socketfd], 0, callback=self._callback, result=result)
        else:
            # proactor
            if self.users[socketfd].read_once():
                logging.debug("Read success from socket {0}".format(socket))
                self.m_thread_pool.append(self.users[socketfd], 0, callback=self._callback, result=result)
            else:
                logging.error("Read failed from socket {0}".format(socket))
                self.deal_timer(util_timer, socket)

    def deal_write(self, socket):
        socketfd = self._socket_to_fd(socket)
        util_timer = self.users_timer[socketfd].utiltimer
        result = (socket, util_timer)
        if self.m_actormodel == 1:
            # reactor
            self.m_thread_pool.append(self.users[socketfd], 1, callback=self._callback, result=result)
        else:
            # proactor
            if self.users[socketfd].write():
                logging.debug("Write success from socket {0}".format(socket))
                self.adjust_timer(util_timer)
            else:
                self.deal_timer(util_timer, socket)

    def event_loop(self):
        logging.info("Start event loop.")
        while not self.m_stop_server:
            ready_events = self.m_epollfd.select()
            logging.debug("Get ready events {0}".format(ready_events))
            for key, event in ready_events:
                socket = key.fileobj
                socketfd = key.data
                if socketfd == self._socket_to_fd(self.m_listen_socket):
                    # 客户端连接
                    if not self.deal_client_data():
                        continue
                elif event & (select.EPOLLRDHUP | select.EPOLLHUP | select.EPOLLERR):
                    # 服务器关闭连接，移除对应的定时器
                    self.deal_timer(self.users_timer[socketfd].utiltimer, socket)
                elif socketfd == self._socket_to_fd(self.m_pipefd_0) and event & select.EPOLLIN:
                    # 处理信号
                    if not self.deal_signal():
                        continue
                elif event & select.EPOLLIN:
                    self.deal_read(socket)
                elif event & select.EPOLLOUT:
                    self.deal_write(socket)
            if self.m_timeout:
                self.utils.timer_handler()
                self.m_timeout = False
        logging.info("Event loop end.")
