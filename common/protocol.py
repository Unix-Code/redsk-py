import struct
from collections.abc import Buffer
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar, Protocol, Self, override


class MsgType(IntEnum):
    GREETINGS = 0
    REGISTRATION = 1
    # GAME_STATE = 3


class NetworkMessage(Protocol):
    # NOTE: Right now, ALL returned offsets are RELATIVE not absolute.
    def pack_into(self, buf: Buffer, offset: int = 0) -> int: ...
    @classmethod
    def unpack_from(cls, buf: Buffer, offset: int = 0) -> tuple[Self, int]: ...
    def pack(self) -> bytes:
        buf = bytearray()
        _ = self.pack_into(buf)
        return bytes(buf)

    @classmethod
    def unpack(cls, b: bytes) -> Self:
        obj, _ = cls.unpack_from(bytearray(b))
        return obj


class TypedNetworkMessage(NetworkMessage, Protocol):
    MESSAGE_TYPE: ClassVar[MsgType]


@dataclass
class MessageHeader(NetworkMessage):
    # Format: [4-byte Length][1-byte Type]
    _HEADER_FORMAT = ">IB"
    HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)

    msg_type: MsgType
    msg_length: int

    @override
    def pack_into(self, buf: Buffer, offset: int = 0) -> int:
        struct.pack_into(
            self._HEADER_FORMAT, buf, offset, self.msg_length, self.msg_type
        )
        return self.HEADER_SIZE

    @classmethod
    @override
    def unpack_from(cls, buf: Buffer, offset: int = 0) -> tuple[Self, int]:
        msg_length, msg_type = struct.unpack_from(cls._HEADER_FORMAT, buf, offset)
        return cls(msg_type=msg_type, msg_length=msg_length), cls.HEADER_SIZE


@dataclass
class StringMessage(NetworkMessage):
    value: str

    @override
    def pack_into(self, buf: Buffer, offset: int = 0) -> int:
        byte_str = self.value.encode("utf-8")
        struct_format = f">H{len(byte_str)}s"
        struct.pack_into(struct_format, buf, offset, len(byte_str), byte_str)
        return struct.calcsize(struct_format)

    @classmethod
    @override
    def unpack_from(cls, buf: Buffer, offset: int = 0) -> tuple[Self, int]:
        start_offset = offset
        str_len_format = f">H"
        (str_len,) = struct.unpack_from(str_len_format, buf, offset)
        offset += struct.calcsize(str_len_format)
        (byte_str,) = struct.unpack_from(f">{str_len}s", buf, offset)
        offset += str_len
        return cls(value=byte_str.decode("utf-8")), offset - start_offset


@dataclass
class GreetingsMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.GREETINGS
    player_id: str  # UUID
    player_name: str

    def pack_into(self, buf: Buffer, offset: int = 0) -> int:
        start_offset = offset
        offset += StringMessage(value=self.player_id).pack_into(buf, offset)
        offset += StringMessage(value=self.player_name).pack_into(buf, offset)
        return offset - start_offset

    @classmethod
    def unpack_from(cls, buf: Buffer, offset: int = 0) -> tuple[Self, int]:
        start_offset = offset
        id_str_msg, offset_delta_1 = StringMessage.unpack_from(buf, offset)
        offset += offset_delta_1

        name_str_msg, offset_delta_2 = StringMessage.unpack_from(buf, offset)
        offset += offset_delta_2

        return cls(
            player_id=id_str_msg.value, player_name=name_str_msg.value
        ), offset - start_offset


@dataclass
class RegistrationMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.REGISTRATION
    name: str

    def pack_into(self, buf: Buffer, offset: int = 0) -> int:
        offset = StringMessage(value=self.name).pack_into(buf, offset)
        return offset

    @classmethod
    def unpack_from(cls, buf: Buffer, offset: int = 0) -> tuple[Self, int]:
        str_msg, offset = StringMessage.unpack_from(buf, offset)
        return cls(name=str_msg.value), offset
