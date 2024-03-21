import select
import socket
import http_config


class HttpConnect():
    m_epollfd = None
    m_user_count = 0

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

    def _addfd(self, socket, one_shot=False, trigmode=0):
        """注册socket到内核事件监控.
        
        trigmode=1: 边缘触发模式 EPOLLET
        trigmode=0: 水平触发模式
        """
        if trigmode == 1:
            events = select.EPOLLIN | select.EPOLLET | select.EPOLLRDHUP
        else:
            events = select.EPOLLIN | select.EPOLLRDHUP
        if one_shot:
            events |= select.EPOLLONESHOT
        data = self._socket_to_fd(socket)
        self.m_epollfd.register(socket, events, data)
        socket.setblocking(False)

    def _removefd(self, socket):
        """删除内核事件监控中的socket.

        """
        self.m_epollfd.unregister(socket)

    def _modityfd(self, socket, event, trigmode):
        """修改socket监听的事件.

        trigmode=1: 边缘触发模式 EPOLLET
        trigmode=0: 水平触发模式
        """
        if trigmode == 1:
            events = event | select.EPOLLET | select.EPOLLRDHUP | select.EPOLLONESHOT
        else:
            events = event | select.EPOLLRDHUP | select.EPOLLONESHOT
        data = self._socket_to_fd(socket)
        self.m_epollfd.modify(socket, events, data)

    def close_connection(self, socket):
        self._removefd(socket)
        self.m_user_count -= 1

    def init(self, client_socket, trigmode):
        # 实例变量初始化
        self.trigmode = trigmode
        self.client_socket = client_socket
        self.m_start_line = 0
        self.m_checked_idx = 0
        self.m_read_idx = 0
        self.m_write_idx = 0
        self.m_read_buf = b''
        self.m_write_buf = b''
        self.m_method = http_config.METHOD.GET
        self.m_url = 0
        self.m_version = 0
        # 添加事件监控
        self._addfd(socket=client_socket, one_shot=True, trigmode=trigmode)
        # 记录总的客户端连接数
        self.m_user_count += 1
        # http 解析主状态机的初始状态
        self.m_check_state = http_config.CHECK_STATE.CHECK_STATE_REQUESTLINE
        
    def _parse_line(self):
        """解析一行的读取状态.

        http 请求报文每一行都以 \r\n 结尾
        """
        while self.m_checked_idx < self.m_read_idx:
            tmp = self.m_read_buf[self.m_checked_idx]
            if tmp == b'\r'[0]:
                if self.m_checked_idx + 1 == self.m_read_idx:
                    # \r 是当前缓存最后一个字符，说明接收数据不完整，需要继续接收
                    return http_config.LINE_STATUS.LINE_OPEN
                elif self.m_read_buf[self.m_checked_idx + 1] == b'\n'[0]:
                    self.m_read_buf.replace(b'\r', b'\0', 1)
                    self.m_read_buf.replace(b'\n', b'\0', 1)
                    self.m_checked_idx += 2
                    return http_config.LINE_STATUS.LINE_OK
                return http_config.LINE_STATUS.LINE_BAD
            if tmp == b'\n'[0]:
                if self.m_checked_idx > 1 and self.m_read_buf[self.m_checked_idx - 1] == b'\r'[0]:
                    self.m_read_buf.replace(b'\r', b'\0', 1)
                    self.m_read_buf.replace(b'\n', b'\0', 1)
                    self.m_checked_idx += 1
                    return http_config.LINE_STATUS.LINE_OK
        return http_config.LINE_STATUS.LINE_OPEN

    def _parse_request_line(self, text):
        """解析请求行，获取请求方法，url，http版本等信息.

        text: 表示一行的字节对象
        """

    def _process_read(self):
        """读和处理请求报文.

        """
        line_status = http_config.LINE_STATUS.LINE_OK
        ret = http_config.HTTP_CODE.NO_REQUEST

    def _read_by_lt_mode(self):
        """LT模式读取数据.

        """
        chunk = self.client_socket.recv(http_config.buffer["read_buffer_size"] - self.m_read_idx)
        if chunk:
            self.m_read_buf += chunk
        else:
            # 客户端连接关闭
            return False
        # 更新当前客户端已读字节数
        self.m_read_idx += len(chunk)
        return True

    def _read_by_et_mode(self):
        """ET模式读取数据.

        """
        while True:
            try:
                chunk = self.client_socket.recv(http_config.buffer["read_buffer_size"] - self.m_read_idx)
                if chunk:
                    self.m_read_buf += chunk
                else:
                    # 客户端连接关闭
                    return False
                self.m_read_idx += len(chunk)
            except socket.error as e:
                if e.errno == socket.EWOULDBLOCK or e.errno == socket.EAGAIN:
                    # 数据读完
                    break
                return False
        return True

    def read_once(self):
        """读取客户端发送的数据.

        """
        if self.m_read_idx >= http_config.buffer["read_buffer_size"]:
            return False
        if self.trigmode == 0:
            # LT 触发模式读取
            return self._read_by_lt_mode()
        else:
            # ET 触发模式读取
            return self._read_by_et_mode()
