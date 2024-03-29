import socket

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(("127.0.0.1", 9006))
client_socket.setblocking(False)
print("default send buffer: ", client_socket.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF))
client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)
print("modify send buffer: ", client_socket.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF))
send_bytes = "-".join(["hello server!"] * 40000).encode()
total_size = len(send_bytes)
print("Total size ", total_size)
have_send_bytes = 0
while True:
    try:
        bytes_send = client_socket.send(send_bytes[-total_size:])
    except socket.error as e:
        if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
            print("Send buffer is full")
            print("Send bytes: ", have_send_bytes)
            continue
        print(e)
        print("Send bytes: ", have_send_bytes)
        exit(1)
    total_size -= bytes_send
    have_send_bytes += bytes_send
    if total_size <= 0:
        print("Send completed")
        break
print("send bytes: ", have_send_bytes)
client_socket.close()
