import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("0.0.0.0", 9006))
server_socket.listen(5)
# server_socket.setblocking(False)
try:
    client_socket, client_addr = server_socket.accept()
except socket.error as e:
    if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
        print(e)
    exit(1)
client_socket.setblocking(False)

recv = ""
chunk = None
while True:
    try:
        chunk = client_socket.recv(1024)
        if not chunk:
            print("Client is closed")
            break
        recv += chunk.decode()
    except socket.error as e:
        if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
            if chunk is None:
                continue
            print("Data receive completed")
            # break
            continue
        exit(1)
print("Reveive bytes: ", len(recv.encode()))

server_socket.close()
