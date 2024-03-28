import math
import selectors


class MyEpollSelector(selectors.EpollSelector):
    """拓展注册监听的事件类型.
    
    默认支持事件类型:
        select.EPOLLIN
        select.EPOLLOUT
    拓展的事件类型:
        select.EPOLLET
        select.EPOLLRDHUP
        select.EPOLLONESHOT
        ...
    """
    def register(self, fileobj, events, data=None):
        key = selectors.SelectorKey(fileobj, self._fileobj_lookup(fileobj), events, data)
        if key.fd in self._fd_to_key:
            raise KeyError("{!r} (FD {}) is already registered".format(fileobj, key.fd))
        self._fd_to_key[key.fd] = key
        poller_events = 0
        poller_events |= events
        try:
            self._selector.register(key.fd, poller_events)
        except:
            super().unregister(fileobj)
            raise
        return key

    def modify(self, fileobj, events, data=None):
        try:
            key = self._fd_to_key[self._fileobj_lookup(fileobj)]
        except KeyError:
            raise KeyError(f"{fileobj!r} is not registered") from None

        changed = False
        if events != key.events:
            selector_events = 0
            selector_events |= events
            try:
                self._selector.modify(key.fd, selector_events)
            except:
                super().unregister(fileobj)
                raise
            changed = True
        if data != key.data:
            changed = True

        if changed:
            key = key._replace(events=events, data=data)
            self._fd_to_key[key.fd] = key
        return key

    def select(self, timeout=None):
        if timeout is None:
            timeout = -1
        elif timeout <= 0:
            timeout = 0
        else:
            # epoll_wait() has a resolution of 1 millisecond, round away
            # from zero to wait *at least* timeout seconds.
            timeout = math.ceil(timeout * 1e3) * 1e-3

        # epoll_wait() expects `maxevents` to be greater than zero;
        # we want to make sure that `select()` can be called when no
        # FD is registered.
        max_ev = max(len(self._fd_to_key), 1)

        ready = []
        try:
            fd_event_list = self._selector.poll(timeout, max_ev)
        except InterruptedError:
            return ready
        for fd, event in fd_event_list:
            key = self._key_from_fd(fd)
            if key:
                ready.append((key, event & key.events))
        return ready
