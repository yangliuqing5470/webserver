from concurrent import futures


class ThreadPool():
    def __init__(self, actor_model, thread_num):
        self.m_actor_model = actor_model
        self.m_thread_num = thread_num
        self.m_threadpool = futures.ThreadPoolExecutor(self.m_thread_num)

    def append(self, request, state=0, callback=None, result=tuple()):
        """往线程池追加一个任务.

        request: httpconnect 对象
        state: 0表示读，1表示写
        """
        request.m_state = state
        future = self.m_threadpool.submit(self.worker, request, result)
        if callback:
            future.add_done_callback(callback)

    def worker(self, request, result):
        """线程工作函数.

        """
        new_result = None
        if self.m_actor_model == 1:
            # reactor
            if request.m_state == 0:
                if request.read_once():
                    request.process()
                    new_result = (1, *result)
                else:
                    new_result = (0, *result)
            else:
                if request.write():
                    new_result = (1, *result)
                else:
                    new_result = (0, *result)
        else:
            # proactor
            request.process()
            new_result = (1, *result)
        return new_result
