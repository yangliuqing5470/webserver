import os
import logging
import getopt
import sys
import webserver


class Config():
    port = 9006
    # 默认触发组合模式：listenfd LT, connfd: LT
    trigmode = 0
    # 线程池初始值
    thread_num = 8
    # 默认不使用优雅关闭连接
    opt_linger = 0
    # 日志 level: 0: debug, 1: info, 2: >=warn
    log_level = 1
    # 默认使用 proactor 模式
    actor_model = 0

def parase_args():
    config = Config()
    shortopts = "p:m:o:t:l:a:"
    opts, _ = getopt.getopt(sys.argv[1:], shortopts)
    for opt, arg_value in opts:
        if opt == "-p":
            config.port = int(arg_value)
        elif opt == "-m":
            config.trigmode = int(arg_value)
        elif opt == "-o":
            config.opt_linger = int(arg_value)
        elif opt == "-t":
            config.thread_num = int(arg_value)
        elif opt == "-l":
            config.log_level = int(arg_value)
        elif opt == "-a":
            config.actor_model = int(arg_value)
        else:
            continue
    return config

def set_log(log_level):
    log_level_map = {
        "0": logging.DEBUG,
        "1": logging.INFO,
        "2": logging.WARN
    }
    log_path = os.path.join(os.getcwd(), "app.log")
    if os.path.exists(log_path):
        os.remove(log_path)
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))
    logformat = "%(asctime)s|%(levelname)s|%(process)d|%(message)s"
    DATE_FORMAT = '%Y-%m-%d  %H:%M:%S'
    logging.basicConfig(level=log_level_map[str(log_level)], format=logformat, datefmt = DATE_FORMAT, filename=log_path)


def main():
    config = parase_args()
    set_log(config.log_level)
    args = {
        "port": config.port,
        "thread_num": config.thread_num,
        "opt_linger": config.opt_linger,
        "trigmode": config.trigmode,
        "actormodel": config.actor_model
    }
    server = webserver.WebServer(args)
    server.sql_pool()
    server.trig_mode()
    server.thread_pool()
    server.event_listen()
    server.event_loop()


if __name__ == "__main__":
    main()
