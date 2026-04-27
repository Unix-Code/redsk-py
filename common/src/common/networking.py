import errno
import logging
import selectors
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from socket import AF_INET, SO_ERROR, SOCK_STREAM, SOL_SOCKET, socket
from typing import TypeAlias, cast

from common.protocol import (
    MessageHeader,
    MessageHeaderCodec,
    MsgType,
    TypedNetworkMessage,
    pack_network_message_into,
)

logging.basicConfig(level=logging.INFO)


_KILOBYTE = 1024
BUFFER_SIZE = 128 * _KILOBYTE


ClientId: TypeAlias = str


class ConnectionState(Enum):
    IDLE = auto()
    IN_PROGRESS = auto()
    CONNECTED = auto()
    FAILED = auto()  # Covers connection failure AND disconnected

    @property
    def is_terminal(self) -> bool:
        return self in (ConnectionState.CONNECTED, ConnectionState.FAILED)


@dataclass
class Connection:
    addr: tuple[str, int]
    sock: socket
    client_id: ClientId = field(default_factory=lambda: str(uuid.uuid4()))
    state: ConnectionState = ConnectionState.IN_PROGRESS

    in_buf: bytearray = field(default_factory=lambda: bytearray(BUFFER_SIZE))
    in_cursor: int = 0
    out_buf: bytearray = field(default_factory=lambda: bytearray(BUFFER_SIZE))
    out_cursor: int = 0

    @property
    def host(self) -> str:
        return self.addr[0]

    @property
    def port(self) -> int:
        return self.addr[1]


MessagePayloads: TypeAlias = list[tuple[MsgType, bytes]]


class CommonNetworking:
    def __init__(self, selector: selectors.DefaultSelector) -> None:
        self.selector = selector
        self.interfaces: dict[str, Connection] = {}
        self._msg_header_codec = MessageHeaderCodec()

    def add_interface(self, client_id: ClientId, connection: Connection) -> None:
        self.interfaces[client_id] = connection

    def send_message(self, client_id: ClientId, msg: TypedNetworkMessage) -> None:
        if client_id not in self.interfaces:
            logging.error("Cannot send message to unknown client: %s", client_id)
            return

        msg_packed = pack_network_message_into(
            obj=msg,
            buf=self.interfaces[client_id].out_buf,
            # HACK: Leave an empty slot for the header
            offset=self.interfaces[client_id].out_cursor
            + MessageHeaderCodec.HEADER_SIZE,
        )

        header_packed = self._msg_header_codec.pack_into(
            MessageHeader(msg_type=msg.MESSAGE_TYPE, msg_length=msg_packed),
            self.interfaces[client_id].out_buf,
            self.interfaces[client_id].out_cursor,
        )

        self.interfaces[client_id].out_cursor += header_packed + msg_packed
        # Explicitly retrigger the listening for writes...
        self.selector.modify(
            self.interfaces[client_id].sock,
            selectors.EVENT_READ | selectors.EVENT_WRITE,
            data=self.interfaces[client_id],
        )

    def close_connection(self, msg: str, client_id: str) -> None:
        logging.info("Client(%s): %s", client_id, msg)
        conn = self.interfaces[client_id]
        conn.state = ConnectionState.FAILED
        self.selector.unregister(conn.sock)
        conn.sock.close()

    def _finish_connect(self, conn: Connection) -> None:
        err = conn.sock.getsockopt(SOL_SOCKET, SO_ERROR)

        if err != 0:
            conn.state = ConnectionState.FAILED
            self.close_connection("Connection failed", conn.client_id)
            return

        logging.info("Connection established: %s", conn.addr)
        conn.state = ConnectionState.CONNECTED
        # Now, listen normally
        self.selector.modify(conn.sock, selectors.EVENT_READ, data=conn)

    def service_connection(
        self, key: selectors.SelectorKey, mask: int
    ) -> tuple[ClientId, MessagePayloads]:
        sock = cast(socket, key.fileobj)
        conn_data = cast(Connection, key.data)
        payloads: list[tuple[MsgType, bytes]] = []

        # HANDLE CONNECT COMPLETION
        if (
            conn_data.state == ConnectionState.IN_PROGRESS
            and mask & selectors.EVENT_WRITE
        ):
            _ = self._finish_connect(conn_data)
            return conn_data.client_id, payloads

        if mask & selectors.EVENT_READ:
            try:
                # Read directly into the pre-allocated buffer starting at index 0
                # recv_into avoids creating a new bytes object for every read
                in_buf_view = memoryview(conn_data.in_buf)[conn_data.in_cursor :]
                nbytes = sock.recv_into(in_buf_view)

                if nbytes == 0:
                    self.close_connection(
                        "Closing connection due to receiving no bytes",
                        conn_data.client_id,
                    )
                    return conn_data.client_id, payloads
                conn_data.in_cursor += nbytes

                logging.info("Reading...")

                # PROCESS ALL COMPLETE MESSAGES IN THE BUFFER
                processed_bytes = 0
                while (
                    conn_data.in_cursor - processed_bytes
                ) >= self._msg_header_codec.HEADER_SIZE:
                    # 1. Peek at the header to see how much more data we need
                    msg_header, read_offset = self._msg_header_codec.unpack_from(
                        conn_data.in_buf
                    )

                    # Total bytes needed = Header + Message (msg_len)
                    total_expected = read_offset + msg_header.msg_length

                    if (conn_data.in_cursor - processed_bytes) >= total_expected:
                        # 2. We have a full message! Extract the payload
                        payload = conn_data.in_buf[read_offset:total_expected]
                        payloads.append((msg_header.msg_type, bytes(payload)))
                        processed_bytes += read_offset + len(payload)
                    else:
                        # Not enough data yet, wait for next EVENT_READ
                        break

                # SHIFT: If we processed anything, move the "leftover" partial msg to index 0
                if processed_bytes > 0:
                    remaining_bytes = conn_data.in_cursor - processed_bytes
                    if remaining_bytes > 0:
                        conn_data.in_buf[:remaining_bytes] = conn_data.in_buf[
                            processed_bytes : conn_data.in_cursor
                        ]
                    conn_data.in_cursor = remaining_bytes

            except OSError as e:
                if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                    self.close_connection(
                        f"Error reading from connection {conn_data.addr}: {e}",
                        conn_data.client_id,
                    )
                    return conn_data.client_id, payloads

        if mask & selectors.EVENT_WRITE and conn_data.out_buf:
            logging.info("Writing...")
            try:
                out_buf_view = memoryview(conn_data.out_buf)[: conn_data.out_cursor]
                sent = sock.send(out_buf_view)

                if sent < conn_data.out_cursor:
                    # Shift remaining unsent data to the front
                    remaining_bytes = conn_data.out_cursor - sent
                    conn_data.out_buf[:remaining_bytes] = conn_data.out_buf[
                        sent : conn_data.out_cursor
                    ]
                    conn_data.out_cursor = remaining_bytes
                else:
                    conn_data.out_cursor = 0
                    # Stop listening for writes to save CPU
                    self.selector.modify(
                        conn_data.sock, selectors.EVENT_READ, data=conn_data
                    )
            except OSError as e:
                if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                    self.close_connection(
                        f"Error writing to connection {conn_data.addr}: {e}",
                        conn_data.client_id,
                    )
                    return conn_data.client_id, payloads

        return conn_data.client_id, payloads


class ClientNetworking:
    _SERVER_ID = "<SERVER>"

    def __init__(self) -> None:
        self._state: ConnectionState = ConnectionState.IDLE
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.setblocking(False)
        self.selector = selectors.DefaultSelector()
        self.common_networking = CommonNetworking(selector=self.selector)
        self.selector.register(self.sock, selectors.EVENT_READ, data=None)

    def reset(self) -> None:
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.setblocking(False)
        self.selector = selectors.DefaultSelector()
        self.common_networking = CommonNetworking(selector=self.selector)
        self.selector.register(self.sock, selectors.EVENT_READ, data=None)

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    def close(self) -> None:
        if self.sock.fileno() != -1:
            self.selector.unregister(self.sock)
            self.sock.close()
        self.selector.close()

    def connect(self, host: str = "localhost", port: int = 65434) -> None:
        if self.connection_state not in (ConnectionState.IDLE, ConnectionState.FAILED):
            raise AssertionError("Can't connect while connection in progress")
        else:
            self._state = ConnectionState.IN_PROGRESS

        err = self.sock.connect_ex((host, port))
        if err != 0 and err not in (
            errno.EAGAIN,
            errno.EWOULDBLOCK,
            errno.EINPROGRESS,
            errno.EALREADY,
        ):
            logging.error("Unable to connect... Errno: %s", errno.errorcode[err])
            self._state = ConnectionState.FAILED
            return

        new_conn = Connection(
            addr=(host, port), sock=self.sock, client_id=self._SERVER_ID
        )
        self.common_networking.add_interface(new_conn.client_id, new_conn)

        # Wait for connect completion (we know we connected when the sock first becomes writeable)
        self.selector.modify(
            self.sock,
            selectors.EVENT_READ | selectors.EVENT_WRITE,
            data=new_conn,
        )

    def poll(self, timeout: float = 0) -> MessagePayloads:
        # HACK: We should return some sort of event when a close happens in addition to messages...
        if self.sock.fileno() == -1:
            self.close()
            return []

        events = self.selector.select(timeout=timeout)

        all_client_payloads: dict[ClientId, MessagePayloads] = {}
        for key, mask in events:
            if key.data is None:
                # We likely haven't connected yet...
                continue

            client_id, payloads = self.common_networking.service_connection(key, mask)
            conn = self.common_networking.interfaces.get(client_id)
            if conn is not None:
                if conn.state == ConnectionState.CONNECTED:
                    self._state = ConnectionState.CONNECTED
                elif conn.state == ConnectionState.FAILED:
                    self._state = ConnectionState.FAILED

            if payloads:
                all_client_payloads[client_id] = payloads

        assert len(all_client_payloads) <= 1

        if not all_client_payloads:
            return []
        return all_client_payloads.popitem()[1]

    def send_message(self, msg: TypedNetworkMessage) -> None:
        return self.common_networking.send_message(client_id=self._SERVER_ID, msg=msg)


class ServerNetworking:
    def __init__(self, host: str = "localhost", port: int = 65434) -> None:
        self.host = host
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.listen_sock = socket(AF_INET, SOCK_STREAM)
        self.listen_sock.bind((self.host, self.port))
        self.listen_sock.listen()
        self.listen_sock.setblocking(False)
        self.selector.register(self.listen_sock, selectors.EVENT_READ, data=None)
        logging.info(f"Listening on {(self.host, self.port)}")
        self.common_networking = CommonNetworking(selector=self.selector)

    def close(self) -> None:
        self.selector.unregister(self.listen_sock)
        self.selector.close()
        self.listen_sock.close()

    def accept_new_connection(self, sock: socket) -> None:
        conn, addr = sock.accept()  # Should be ready to read
        conn.setblocking(False)
        data = Connection(addr=addr, sock=conn, state=ConnectionState.CONNECTED)
        events = selectors.EVENT_READ
        _ = self.selector.register(conn, events, data=data)
        self.common_networking.add_interface(data.client_id, data)
        logging.info("Accepted connection from %s", data.addr)

    def poll(self, timeout: float = 0) -> dict[ClientId, MessagePayloads]:
        # Block until I/O is ready OR it's time for the next game update
        events = self.selector.select(timeout=timeout)

        all_client_payloads: dict[ClientId, MessagePayloads] = {}
        for key, mask in events:
            if key.data is None:
                # New connection ready to be accepted
                self.accept_new_connection(cast(socket, key.fileobj))
            else:
                # Existing connection with data to read or buffer space to write
                client_id, payloads = self.common_networking.service_connection(
                    key, mask
                )
                if payloads:
                    all_client_payloads[client_id] = payloads

        return all_client_payloads

    def send_message(self, client_id: ClientId, msg: TypedNetworkMessage) -> None:
        return self.common_networking.send_message(client_id=client_id, msg=msg)
