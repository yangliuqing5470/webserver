import os
import socket
import signal
import struct
import time
import epoll.epoll as epoll
import timer.lst_timer as lst_timer
import httpconnect.http_connect as http_connect

MAX_FD = 65536
MAX_EVENT_NUMBER = 10000
TIMESLOT = 5

class WebServer():
    def __init__(self, args: dict):
        # 获取root文件夹路径
        self.m_root = os.path.join(os.getcwd(), "root")
        self.users = [http_connect.HttpConnect()] * MAX_FD
        self.users_time = [lst_timer.ClientData()] * MAX_FD
        self.m_port = args["port"]
        self.m_user = args["user"]
        self.m_password = args["password"]
        self.m_databasename = args["databasename"]
        self.m_sql_num = args["sql_num"]
        self.m_thread_num = args["thread_num"]
        self.m_log_write = args["log_write"]
        self.m_opt_linger = args["opt_linger"]
        self.m_trigmode = args["trigmode"]
        self.m_close_log = args["close_log"]
        self.m_actormodel = args["actormodel"]

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
        utils = lst_timer.Utils(TIMESLOT)
        self.m_epollfd = epoll.MyEpollSelector()
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
        signal.alarm(TIMESLOT)
        self.utils = utils

    def timer(self, client_socket, client_address):
        fd = self._socket_to_fd(client_socket)
        self.users[fd].init(client_socket, self.m_trigmode, self.m_root)
        self.users_time[fd].address = client_address
        self.users_time[fd].socket = client_socket
        timer_node = lst_timer.UtilTimer(user_data=self.users_time[fd], cb_func=lst_timer.cb_func)
        cur = time.time()
        timer_node.expire = cur + 3 * TIMESLOT      # type: ignore
        self.users_time[fd].utiltimer = timer_node  # type: ignore
        self.utils.m_sorted_timer_list.add_timer(timer_node)

    def adjust_timer(self, timer):
        """如果在过期时间内有数据，则将定时器值往后延3个单位，并调整有序定时器链表.

        """
        cur = time.time()
        timer.expire = cur + 3 * TIMESLOT
        self.utils.m_sorted_timer_list.adjust_timer(timer)

    def deal_timer(self, timer, socket):
        fd = self._socket_to_fd(socket)
        timer.cb_func(self.m_epollfd, self.users_time[fd])
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
        else:
            # ET mode
            pass

    def deal_signal(self):
        pass

    def deal_read(self):
        pass

    def deal_write(self):
        pass
