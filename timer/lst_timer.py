import time
import select
import signal
from httpconnect.http_connect import HttpConnect


class ClientData:
    def __init__(self):
        self.address = None
        self.socket = None
        self.utiltimer = None

class UtilTimer():
    """定时器类，类似链表中的一个节点.

    """
    def __init__(self, user_data, cb_func):
        self.expire = 0
        self.user_data = user_data
        self.cb_func = cb_func
        self.prev = None
        self.next = None

class SortTimerList():
    """有序的定时器链表，以定时器节点过期事件属性升序排序.

    """
    def __init__(self):
        # 链表的头，指向定时器类节点
        self.head = None
        # 链表尾
        self.tail = None

    def _add_timer(self, utiltimer, head):
        """普通情况：插入的定时器过期时间排在已有链表的中间某个位置.

        """
        prev = head
        tmp = head.next
        while tmp is not None:
            if utiltimer.expire < tmp.expire:
                prev.next = utiltimer
                utiltimer.next = tmp
                tmp.prev = utiltimer
                utiltimer.prev = prev
                break
            prev = tmp
            tmp = tmp.next
        if not tmp:
            prev.next = utiltimer
            utiltimer.prev = prev
            utiltimer.next = None
            self.tail = utiltimer

    def add_timer(self, utiltimer):
        if self.head is None:
            self.head = utiltimer
            self.tail = utiltimer
            return
        if utiltimer.expire < self.head.expire:
            utiltimer.next = self.head
            self.head.prev = utiltimer
            self.head = utiltimer
            return
        self._add_timer(utiltimer, self.head)

    def adjust_timer(self, utiltimer):
        """在过期时间内客户端有数据到来，则调整当前客户端绑定的定时器过期时间(往后延固定时间).

        """
        tmp = utiltimer.next
        if not tmp or utiltimer.expire  < tmp.expire:
            return
        if self.head is None:
            self.head = utiltimer
            self.tail = utiltimer
            return None
        if self.head == utiltimer:
            self.head = self.head.next
            self.head.prev = None
            utiltimer.next = None
            self._add_timer(utiltimer, self.head)
        else:
            utiltimer.prev.next = utiltimer.next
            utiltimer.next.prev = utiltimer.prev
            self._add_timer(utiltimer, self.head)
            
    def del_timer(self, utiltimer):
        if self.head is None or self.tail is None:
            return
        if self.head == utiltimer and self.tail == utiltimer:
            self.head = None
            self.tail = None
            return
        if self.head == utiltimer:
            self.head = self.head.next
            self.head.prev = None
            return
        if self.tail == utiltimer:
            self.tail = self.tail.prev
            self.tail.next = None
            return
        utiltimer.prev.next = utiltimer.next
        utiltimer.next.prev = utiltimer.prev

    def tick(self):
        """每个定时信号SIGALRM被触发，此函数被调用一次.

        找到过期的定时器处理
        """
        if self.head is None:
            return
        cur = time.time()
        tmp = self.head
        while tmp is not None:
            if cur < tmp.expire:
                break
            # 执行定时器回调函数
            tmp.cb_func(tmp.user_data)
            self.head = tmp.next
            if self.head is not None:
                self.head.prev = None
            tmp = self.head

class Utils():
    def __init__(self, timeslot):
        self.m_timeslot = timeslot
        self.m_pipefd_write = None
        self.m_sorted_timer_list = SortTimerList()

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

    def addfd(self, m_epollfd, socket, one_shot=False, trigmode=0):
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
        m_epollfd.register(socket, events, data)
        socket.setblocking(False)

    def sig_handler(self, sig):
        if self.m_pipefd_write is None:
            return
        self.m_pipefd_write.send(str(sig).encode())

    def addsig(self, signum, handler):
        signal.signal(signum, handler)

    def show_error(self, socket, info: str):
        socket.send(info.encode())
        socket.close()

    def timer_handler(self):
        self.m_sorted_timer_list.tick()
        signal.alarm(self.m_timeslot)


def cb_func(m_epollfd, client_data):
    m_epollfd.unregister(client_data.socket)
    client_data.socket.close()
    # 这里不是线程安全的
    HttpConnect.m_user_count -= 1
