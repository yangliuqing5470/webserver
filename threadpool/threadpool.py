from concurrent import futures


class ThreadPool():
    def __init__(self, actor_model, thread_num):
        self.m_actor_model = actor_model
        self.m_thread_num = thread_num
        self.m_threadpool = futures.ThreadPoolExecutor(self.m_thread_num)

    def append(self, request, state=0):
        """往线程池追加一个任务.

        request: httpconnect 对象
        state: 0表示读，1表示写
        """
        request.m_state = state
        self.m_threadpool.submit(self.worker, request)

    def worker(self, request):
        """线程工作函数.

        """
        if self.m_actor_model == 1:
            # reactor
            if request.m_state == 0:
                if request.read_once():
                    request.mprov = 1
                    request.process()
                else:
                    request.mprov = 1
                    request.timer_flag = 1
            else:
                if request.write():
                    request.mprov = 1
                else:
                    request.mprov = 1
                    request.timer_flag = 1
        else:
            # proactor
            request.process()
