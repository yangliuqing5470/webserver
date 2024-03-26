import os
import mmap
import logging
import stat
import select
import socket
import httpconnect.http_config as http_config  # type: ignore


class HttpConnect():
    m_epollfd = None
    m_user_count = 0
    m_database = None

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
        self.m_epollfd.register(socket, events, data)  # type: ignore
        socket.setblocking(False)

    def _removefd(self, socket):
        """删除内核事件监控中的socket.

        """
        self.m_epollfd.unregister(socket)  # type: ignore

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
        self.m_epollfd.modify(socket, events, data)  # type: ignore

    def close_connection(self, socket):
        self._removefd(socket)
        self.m_user_count -= 1

    def init(self, client_socket, trigmode, root):
        # 实例变量初始化
        self.trigmode = trigmode
        self.client_socket = client_socket
        self.m_start_line = 0
        self.m_checked_idx = 0
        self.m_read_idx = 0
        self.m_write_idx = 0
        self.bytes_to_send = 0
        self.m_read_buf = b''
        self.m_write_buf = b''
        self.m_method = http_config.METHOD.GET
        self.m_url = ""
        self.m_version = 0
        self.cgi = 0
        self.m_host = ""
        # 请求 body 的大小
        self.m_content_length = 0
        # 请求数据
        self.m_string = ""
        # 表示是否是长连接
        self.m_linger = False
        # 服务根目录
        self.doc_root = root
        # 请求资源文件的属性
        self.m_file_stat = None
        # 请求资源文件内存映射对象
        self.m_file_mmap = None
        # 添加事件监控
        self._addfd(socket=client_socket, one_shot=True, trigmode=trigmode)
        # 记录总的客户端连接数
        self.m_user_count += 1
        # http 解析主状态机的初始状态
        self.m_check_state = http_config.CHECK_STATE.CHECK_STATE_REQUESTLINE
        # 0表示当前的请求是读，1表示当前的请求是写(reactor模式)
        self.m_state = 0
        # 0表示不删除定时器，1表示删除定时器(reactor模式)
        self.timer_flag = 0
        # 0表示当前读或者写操作未开始，1表示当前读写操作完成(reactor模式)
        self.improv = 0

    def _get_line(self):
        """获取一行的接收数据.
        
        返回的每一行数据不包含 \r\n ,空行除外
        """
        text_bytes = b''
        # 先处理空行的情况
        if self.m_read_buf[self.m_start_line] == b'\r'[0] and self.m_read_buf[self.m_start_line + 1] == b'\n'[0]:
            text = "\r\n"
            return text
        for idx in range(self.m_start_line, self.m_read_idx):
            if self.m_read_buf[idx] == b'\r'[0] and self.m_read_buf[idx+1] == b'\n'[0]:
                break
            text_bytes = self.m_read_buf[self.m_start_line:self.m_start_line + idx]
        return text_bytes.decode()
        
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
                    self.m_checked_idx += 2
                    return http_config.LINE_STATUS.LINE_OK
                return http_config.LINE_STATUS.LINE_BAD
            if tmp == b'\n'[0]:
                if self.m_checked_idx > 1 and self.m_read_buf[self.m_checked_idx - 1] == b'\r'[0]:
                    self.m_checked_idx += 1
                    return http_config.LINE_STATUS.LINE_OK
                return http_config.LINE_STATUS.LINE_BAD
            self.m_checked_idx += 1
        return http_config.LINE_STATUS.LINE_OPEN

    def _parse_request_line(self, text):
        """解析请求行，获取请求方法，url，http版本等信息.

        text: 表示一行的字符串对象
        """
        if " " not in text or "\t" not in text:
            return http_config.HTTP_CODE.BAD_REQUEST
        # 确定一行的分割符是 " " 还是 "\t"
        separator = " " if " " in text else "\t"
        line_elems_original = text.split(separator)
        # 去掉分割后列表中的分割符
        line_elems = [item for item in line_elems_original if item != separator]
        if line_elems[0] == "GET":
            self.m_method = http_config.METHOD.GET
        elif line_elems[0] == "POST":
            self.m_method = http_config.METHOD.POST
            self.cgi = 1
        else:
            return http_config.HTTP_CODE.BAD_REQUEST
        if line_elems[-1] != "HTTP/1.1":
            return http_config.HTTP_CODE.BAD_REQUEST
        self.m_version = line_elems[-1]
        self.m_url = line_elems[1]
        # 如果有协议头，去掉协议头
        if "http://" in self.m_url:
            self.m_url = self.m_url[7:]
        if "https://" in self.m_url:
            self.m_url = self.m_url[8:]
        if "/" not in self.m_url:
            return http_config.HTTP_CODE.BAD_REQUEST
        # url 更新为第一次 / 及后面的内容
        tmp = self.m_url.split("/")
        tmp[0] = ""
        self.m_url = "/".join(tmp)
        # 当 url 为 / 时，显示 judge.html
        if self.m_url == "/":
            self.m_url += "judge.html"
        self.m_check_state = http_config.CHECK_STATE.CHECK_STATE_HEADER
        # 返回请求不完整状态码
        return http_config.HTTP_CODE.NO_REQUEST

    def _parse_headers(self, text):
        """解析请求头.

        text: 表示一行的字符串对象
        """
        if text == "\r\n":
            # 空行
            if self.m_content_length != 0:
                # POST 请求
                self.m_check_state = http_config.CHECK_STATE.CHECK_STATE_CONTENT
                return http_config.HTTP_CODE.NO_REQUEST
            # GET 请求
            return http_config.HTTP_CODE.GET_REQUEST
        elif "Connection:" in text and "keep-alive" in text:
            self.m_linger = True
        elif "Content-Length:" in text:
            separator = " " if " " in text else "\t"
            self.m_content_length = int(text[15:].replace(separator, ""))
        elif "Host:" in text:
            separator = " " if " " in text else "\t"
            self.m_host = text[5:].replace(separator, "")
        else:
            logging.info("Unknow header!!!")
        return http_config.HTTP_CODE.NO_REQUEST

    def _parse_content(self):
        """解析消息体.
        
        text: 表示消息体的内容
        """
        if self.m_read_idx >= self.m_content_length + self.m_checked_idx:
            # 读 buffer 中已经包含了消息体
            m_string_bytes = self.m_read_buf[self.m_start_line:self.m_start_line + self.m_content_length]
            self.m_string = m_string_bytes.decode()
            return http_config.HTTP_CODE.GET_REQUEST
        return http_config.HTTP_CODE.NO_REQUEST

    def _do_request(self):
        """数据接收完成开始处理请求.

        """
        # 请求的文件在服务器上的路径
        m_real_file = ""
        # 提取请求url中，最右 / 以及后面的字符串
        p = "/{0}".format(self.m_url.rsplit("/", 1)[-1])
        if self.cgi == 1 and p[1] == "2":
            # 登录校验
            # 1. 从请求数据提取用户名和密码 (user=name&password=12121)
            user_name = self.m_string.split("&")[0].split("=")[-1].rstrip()
            password = self.m_string.split("&")[1].split("=")[-1].rstrip()
            # 2. 校验用户名和密码
            if self.m_database and self.m_database.query(user_name) == password: # success
                m_real_file = os.path.join(self.doc_root, "welcome.html")
            else:
                m_real_file = os.path.join(self.doc_root, "logError.html")
        elif self.cgi == 1 and p[1] == "3":
            # 注册校验
            # 1. 从请求数据提取用户名和密码 (user=name&password=12121)
            user_name = self.m_string.split("&")[0].split("=")[-1].rstrip()
            password = self.m_string.split("&")[1].split("=")[-1].rstrip()
            # 2. 检查是否已经注册，已经注册返回注册错误页面
            if self.m_database and self.m_database.query(user_name): # 已经注册
                m_real_file = os.path.join(self.doc_root, "registerError.html")
            else:
                if self.m_database and self.m_database.register(user_name, password):
                    m_real_file = os.path.join(self.doc_root, "log.html")
                else:
                    m_real_file = os.path.join(self.doc_root, "registerError.html")
        elif p[1] == "0":
            m_real_file = os.path.join(self.doc_root, "register.html")
        elif p[1] == "1":
            m_real_file = os.path.join(self.doc_root, "log.html")
        elif p[1] == "5":
            m_real_file = os.path.join(self.doc_root, "picture.html")
        elif p[1] == "6":
            m_real_file = os.path.join(self.doc_root, "video.html")
        elif p[1] == "7":
            m_real_file = os.path.join(self.doc_root, "fans.html")
        else:
            m_real_file = os.path.join(self.doc_root, self.m_url[1:])
        try:
            self.m_file_stat = os.stat(m_real_file)
        except Exception:
            return http_config.HTTP_CODE.NO_RESOURCE
        if not (self.m_file_stat.st_mode & stat.S_IROTH):
            return http_config.HTTP_CODE.FORBIDDEN_REQUEST
        if stat.S_ISDIR(self.m_file_stat.st_mode):
            return http_config.HTTP_CODE.BAD_REQUEST
        # 开始文件内存映射
        with open(m_real_file, "r+b") as f:
            self.m_file_mmap = mmap.mmap(f.fileno(), self.m_file_stat.st_size, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ)
        return http_config.HTTP_CODE.FILE_REQUEST

    def _ummap(self):
        if self.m_file_mmap is not None:
            self.m_file_mmap.close()
            self.m_file_mmap = None

    def _process_read(self):
        """读和处理请求报文.

        """
        line_status = http_config.LINE_STATUS.LINE_OK
        ret = http_config.HTTP_CODE.NO_REQUEST
        text = ""
        while (self.m_check_state == http_config.CHECK_STATE.CHECK_STATE_CONTENT and line_status == http_config.LINE_STATUS.LINE_OK) or self._parse_line() == http_config.LINE_STATUS.LINE_OK:
            if self.m_check_state != http_config.CHECK_STATE.CHECK_STATE_CONTENT:
                # 处理请求行和请求头阶段需要获取每一行处理的数据
                text = self._get_line()
                self.m_start_line = self.m_checked_idx
            if self.m_check_state == http_config.CHECK_STATE.CHECK_STATE_REQUESTLINE:
                ret = self._parse_request_line(text)
                if ret == http_config.HTTP_CODE.BAD_REQUEST:
                    return http_config.HTTP_CODE.BAD_REQUEST
            elif self.m_check_state == http_config.CHECK_STATE.CHECK_STATE_HEADER:
                ret = self._parse_headers(text)
                if ret == http_config.HTTP_CODE.BAD_REQUEST:
                    return http_config.HTTP_CODE.BAD_REQUEST
                elif ret == http_config.HTTP_CODE.GET_REQUEST:
                    # 解析完 GET 请求，开始处理
                    return self._do_request()
            elif self.m_check_state == http_config.CHECK_STATE.CHECK_STATE_CONTENT:
                ret = self._parse_content()
                if ret == http_config.HTTP_CODE.GET_REQUEST:
                    return self._do_request()
                line_status = http_config.LINE_STATUS.LINE_OPEN
            else:
                return http_config.HTTP_CODE.INTERNAL_ERROR
        return http_config.HTTP_CODE.NO_REQUEST

    def _read_by_lt_mode(self):
        """LT模式读取数据.

        """
        chunk = self.client_socket.recv(http_config.buffer["read_buffer_size"] - self.m_read_idx)
        if chunk:
            self.m_read_buf += chunk
        else:
            # 客户端连接关闭
            return False
        # 更新当前客户端已读字符数
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

    def write(self):
        if self.bytes_to_send == 0:
            self._modityfd(self.client_socket, select.EPOLLIN, self.trigmode)
            self.init(self.client_socket, self.trigmode, self.doc_root)
            return True
        while True:
            try:
                temp = self.client_socket.send(self.m_write_buf[self.bytes_to_send:])
            except socket.error as e:
                if e.errno == socket.EAGAIN:
                    self._modityfd(self.client_socket, select.EPOLLOUT, self.trigmode)
                    return True
                self._ummap()
                return False
            self.bytes_to_send -= temp
            if self.bytes_to_send <= 0:
                self._ummap()
                self._modityfd(self.client_socket, select.EPOLLIN, self.trigmode)
                if self.m_linger:
                    self.init(self.client_socket, self.trigmode, self.doc_root)
                    return True
                else:
                    return False

    def _add_response(self, format: str):
        if self.m_write_idx > http_config.buffer["write_buffer_size"]:
            return False
        format_bytes = format.encode()
        if len(format_bytes) >= http_config.buffer["write_buffer_size"] - 1 - self.m_write_idx:
            return False
        self.m_write_buf += format_bytes
        self.m_write_idx += len(format_bytes)
        return True
    
    def _add_status_line(self, status, title):
        return self._add_response("HTTP/1.1 {0} {1}\r\n".format(status, title))

    def _add_content_length(self, content_len):
        return self._add_response("Content-Length: {0}\r\n".format(content_len))

    def _add_content_type(self):
        return self._add_response("Content-Type: text/html\r\n")

    def _add_linger(self):
        if self.m_linger:
            return self._add_response("Connection: keep-alive\r\n")
        else:
            return self._add_response("Connection: close\r\n")

    def _add_content(self, content):
        return self._add_response(content)

    def _add_blank_line(self):
        return self._add_response("\r\n")

    def _add_headers(self, content_len):
        if not self._add_content_length(content_len):
            return False
        if not self._add_content_type():
            return False
        if not self._add_linger():
            return False
        if not self._add_blank_line():
            return False
        return True

    def _process_write(self, http_code):
        if http_code == http_config.HTTP_CODE.INTERNAL_ERROR:
            if not self._add_status_line(500, http_config.response_message["error_500_title"]):
                return False
            if not self._add_headers(len(http_config.response_message["error_500_form"].encode())):
                return False
            if not self._add_content(http_config.response_message["error_500_form"]):
                return False
        elif http_code == http_config.HTTP_CODE.BAD_REQUEST or http_code == http_code.HTTP_CODE.NO_RESOURCE:
            if not self._add_status_line(404, http_config.response_message["error_404_title"]):
                return False
            if not self._add_headers(len(http_config.response_message["error_404_form"].encode())):
                return False
            if not self._add_content(http_config.response_message["error_404_form"]):
                return False
        elif http_code == http_config.HTTP_CODE.FORBIDDEN_REQUEST:
            if not self._add_status_line(403, http_config.response_message["error_403_title"]):
                return False
            if not self._add_headers(len(http_config.response_message["error_403_form"].encode())):
                return False
            if not self._add_content(http_config.response_message["error_403_form"]):
                return False
        elif http_code == http_config.HTTP_CODE.FILE_REQUEST:
            if not self._add_status_line(200, http_config.response_message["ok_200_title"]):
                return False
            if self.m_file_stat and self.m_file_stat.st_size != 0:
                self.m_write_buf = self.m_write_buf + self.m_file_mmap.read() if self.m_file_mmap else self.m_write_buf
                self.bytes_to_send = self.m_write_idx + self.m_file_stat.st_size
                return True
            else:
                ok_string = "<html><body></body></html>"
                if not self._add_headers(len(ok_string.encode())):
                    return False
                if not self._add_content(ok_string):
                    return False
        else:
            return False
        self.bytes_to_send = self.m_write_idx
        return True

    def process(self):
        read_ret = self._process_read()
        if read_ret == http_config.HTTP_CODE.NO_REQUEST:
            self._modityfd(self.client_socket, select.EPOLLIN, self.trigmode)
            return
        write_ret = self._process_write(read_ret)
        if not write_ret:
            self.close_connection(self.client_socket)
        self._modityfd(self.client_socket, select.EPOLLOUT, self.trigmode)
