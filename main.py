import os
import logging
import getopt
import sys
import webserver


class Config():
    port = 9006
    # 默认同步写日志
    logwrite = 0
    # 默认触发组合模式：listenfd LT, connfd: LT
    trigmode = 0
    # 监听socket 模式默认LT
    listentrigmode = 0
    # 数据库连接池初始值
    sql_num = 8
    # 线程池初始值
    thread_num = 8
    # 客户端 socket 模式默认LT
    conntrigmode = 0
    # 默认不使用优雅关闭连接
    opt_linger = 0
    # 默认不关闭日志
    close_log = 0
    # 默认使用 proactor 模式
    actor_model = 0

def parase_args():
    config = Config()
    shortopts = "p:l:m:o:s:t:c:a:"
    opts, _ = getopt.getopt(sys.argv[1:], shortopts)
    for opt, arg_value in opts:
        if opt == "-p":
            config.port = int(arg_value)
        elif opt == "-l":
            config.logwrite = int(arg_value)
        elif opt == "-m":
            config.trigmode = int(arg_value)
        elif opt == "-o":
            config.opt_linger = int(arg_value)
        elif opt == "-s":
            config.sql_num = int(arg_value)
        elif opt == "-t":
            config.thread_num = int(arg_value)
        elif opt == "-c":
            config.close_log = int(arg_value)
        elif opt == "-a":
            config.actor_model = int(arg_value)
        else:
            continue
    return config

def set_log():
    log_path = os.path.join(os.getcwd(), "app.log")
    if os.path.exists(log_path):
        os.remove(log_path)
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))
    logformat = "%(asctime)s|%(levelname)s|%(process)d|%(message)s"
    DATE_FORMAT = '%Y-%m-%d  %H:%M:%S'
    logging.basicConfig(
        level=logging.INFO,
        format=logformat,
        datefmt = DATE_FORMAT,
        filename=log_path
    )


def main():
    user = "root"
    password = "123"
    databasename = "user"
    set_log()
    config = parase_args()
    args = {
        "port": config.port,
        "user": user,
        "password": password,
        "databasename": databasename,
        "sql_num": config.sql_num,
        "thread_num": config.thread_num,
        "log_write": config.logwrite,
        "opt_linger": config.opt_linger,
        "trigmode": config.trigmode,
        "close_log": config.close_log,
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
