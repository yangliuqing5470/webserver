

class HttpConnect():
    m_epollfd = None

    def addfd(self):
        """注册socket到内核事件监控.

        """
        self.m_epollfd.register()

    def init(self, client_socket):
        # 用于和客户端通信的 socket
        self.client_socket = client_socket
