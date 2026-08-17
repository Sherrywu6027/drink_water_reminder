import json


def send_json_message(sock, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(data).to_bytes(4, byteorder="big") + data)


def recv_exactly(sock, size):
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("连接在消息接收完成前已关闭")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_json_message(sock):
    header = recv_exactly(sock, 4)
    total_size = int.from_bytes(header, byteorder="big")
    payload = recv_exactly(sock, total_size)
    return json.loads(payload.decode("utf-8"))
