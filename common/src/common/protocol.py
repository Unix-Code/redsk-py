import struct
from collections.abc import Buffer
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, ClassVar, Hashable, Protocol, TypeVar, cast, get_args, override

from common.game_state import Biome, Faction, Land, Resource
from common.hex import Hex


class MsgType(IntEnum):
    GREETINGS = 0
    REGISTRATION = 1
    START_GAME = 2
    GAME_STATE = 3


T = TypeVar("T")


class NetworkCodec(Protocol[T]):
    # NOTE: Right now, ALL returned offsets are RELATIVE not absolute.
    def pack_into(self, obj: T, buf: Buffer, offset: int = 0) -> int:
        return offset

    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[T, int]: ...

    def unpack(self, b: bytes) -> T:
        obj, _ = self.unpack_from(bytearray(b))
        return obj


class TypedNetworkMessage(Protocol):
    MESSAGE_TYPE: ClassVar[MsgType]


@dataclass
class MessageHeader:
    msg_type: MsgType
    msg_length: int


class MessageHeaderCodec(NetworkCodec[MessageHeader]):
    # Format: [4-byte Length][1-byte Type]
    _HEADER_FORMAT = ">IB"
    HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)

    @override
    def pack_into(self, obj: MessageHeader, buf: Buffer, offset: int = 0) -> int:
        struct.pack_into(self._HEADER_FORMAT, buf, offset, obj.msg_length, obj.msg_type)
        return self.HEADER_SIZE

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[MessageHeader, int]:
        msg_length, msg_type = struct.unpack_from(self._HEADER_FORMAT, buf, offset)
        return MessageHeader(msg_type=msg_type, msg_length=msg_length), self.HEADER_SIZE


class StringNetworkCodec(NetworkCodec[str]):
    @override
    def pack_into(self, obj: str, buf: Buffer, offset: int = 0) -> int:
        byte_str = obj.encode("utf-8")
        struct_format = f">H{len(byte_str)}s"
        struct.pack_into(struct_format, buf, offset, len(byte_str), byte_str)
        return struct.calcsize(struct_format)

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[str, int]:
        start_offset = offset
        str_len_format = f">H"
        (str_len,) = struct.unpack_from(str_len_format, buf, offset)
        offset += struct.calcsize(str_len_format)
        (byte_str,) = struct.unpack_from(f">{str_len}s", buf, offset)
        offset += str_len
        return byte_str.decode("utf-8"), offset - start_offset


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class DictNetworkCodec(NetworkCodec[dict[K, V]]):
    _SIZE_STRUCT = struct.Struct(">H")

    def __init__(
        self, key_codec: NetworkCodec[K], value_codec: NetworkCodec[V]
    ) -> None:
        self._key_codec = key_codec
        self._value_codec = value_codec

    @override
    def pack_into(self, obj: dict[K, V], buf: Buffer, offset: int = 0) -> int:
        start_offset = offset
        self._SIZE_STRUCT.pack_into(buf, offset, len(obj))
        offset += self._SIZE_STRUCT.size

        keys: list[K] = []
        values: list[V] = []
        for key, value in obj.items():
            keys.append(key)
            values.append(value)

        for key in keys:
            offset += self._key_codec.pack_into(obj=key, buf=buf, offset=offset)
        for value in values:
            offset += self._value_codec.pack_into(obj=value, buf=buf, offset=offset)

        return offset - start_offset

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[dict[K, V], int]:
        start_offset = offset

        dict_size, offset_delta_1 = self._SIZE_STRUCT.unpack_from(buf, offset)
        offset += offset_delta_1

        keys: list[K] = []
        for i in range(dict_size):
            key, offset_delta_2 = self._key_codec.unpack_from(buf, offset)
            keys.append(key)
            offset += offset_delta_2

        values: list[V] = []
        for i in range(dict_size):
            value, offset_delta_2 = self._value_codec.unpack_from(buf, offset)
            values.append(value)
            offset += offset_delta_2

        return {key: value for key, value in zip(keys, values)}, offset - start_offset


E = TypeVar("E", bound=Enum)


class EnumNetworkCodec(NetworkCodec[E]):
    _STRUCT = struct.Struct(">B")

    def __init__(self, enum_cls: type[E]) -> None:
        self._enum_cls: type[E] = enum_cls

    @override
    def pack_into(self, obj: E, buf: Buffer, offset: int = 0) -> int:
        self._STRUCT.pack_into(buf, offset, obj.value)
        return self._STRUCT.size

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[E, int]:
        (enum_val,) = self._STRUCT.unpack_from(buf, offset)
        return self._enum_cls(enum_val), self._STRUCT.size


class PrimitiveStructNetworkCodec(NetworkCodec[T]):
    def __init__(self, struct_format: str) -> None:
        self._struct = struct.Struct(struct_format)

    @override
    def pack_into(self, obj: T, buf: Buffer, offset: int = 0) -> int:
        self._struct.pack_into(buf, offset, obj)
        return self._struct.size

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[T, int]:
        (val,) = self._struct.unpack_from(buf, offset)
        return val, self._struct.size


class HexNetworkCodec(NetworkCodec[Hex]):
    _STRUCT = struct.Struct(">HH")

    @override
    def pack_into(self, obj: Hex, buf: Buffer, offset: int = 0) -> int:
        self._STRUCT.pack_into(buf, offset, obj.q, obj.r)
        return self._STRUCT.size

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[Hex, int]:
        q, r = self._STRUCT.unpack_from(buf, offset)

        return Hex(q=q, r=r), self._STRUCT.size


class LandNetworkCodec(NetworkCodec[Land]):
    def __init__(self) -> None:
        self._biome_codec = EnumNetworkCodec(Biome)
        self._resources_codec = DictNetworkCodec(
            key_codec=EnumNetworkCodec(Resource),
            value_codec=PrimitiveStructNetworkCodec[int](">B"),
        )

    @override
    def pack_into(self, obj: Land, buf: Buffer, offset: int = 0) -> int:
        start_offset = offset
        offset += self._biome_codec.pack_into(obj.biome, buf, offset)
        offset += self._resources_codec.pack_into(obj.resources, buf, offset)
        return offset - start_offset

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[Land, int]:
        start_offset = offset
        biome, offset_delta_1 = self._biome_codec.unpack_from(buf, offset)
        offset += offset_delta_1
        resources, offset_delta_2 = self._resources_codec.unpack_from(buf, offset)
        offset += offset_delta_2
        return Land(biome=biome, resources=resources), offset - start_offset


@dataclass
class GreetingsMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.GREETINGS
    player_id: str  # UUID
    player_name: str


class GreetingsMessageCodec(NetworkCodec[GreetingsMessage]):
    def __init__(self) -> None:
        self._str_codec = StringNetworkCodec()

    @override
    def pack_into(self, obj: GreetingsMessage, buf: Buffer, offset: int = 0) -> int:
        start_offset = offset
        offset += self._str_codec.pack_into(obj=obj.player_id, buf=buf, offset=offset)
        offset += self._str_codec.pack_into(obj=obj.player_name, buf=buf, offset=offset)
        return offset - start_offset

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[GreetingsMessage, int]:
        start_offset = offset
        id_str_msg, offset_delta_1 = self._str_codec.unpack_from(buf, offset)
        offset += offset_delta_1

        name_str_msg, offset_delta_2 = self._str_codec.unpack_from(buf, offset)
        offset += offset_delta_2

        return GreetingsMessage(
            player_id=id_str_msg, player_name=name_str_msg
        ), offset - start_offset


@dataclass
class RegistrationMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.REGISTRATION
    name: str


class RegistrationMessageCodec(NetworkCodec[RegistrationMessage]):
    def __init__(self) -> None:
        self._str_codec = StringNetworkCodec()

    @override
    def pack_into(self, obj: RegistrationMessage, buf: Buffer, offset: int = 0) -> int:
        offset = self._str_codec.pack_into(obj=obj.name, buf=buf, offset=offset)
        return offset

    @override
    def unpack_from(
        self, buf: Buffer, offset: int = 0
    ) -> tuple[RegistrationMessage, int]:
        str_msg, offset = self._str_codec.unpack_from(buf, offset)
        return RegistrationMessage(name=str_msg), offset


@dataclass
class StartGameMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.START_GAME


class StartGameMessageCodec(NetworkCodec[StartGameMessage]):
    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[StartGameMessage, int]:
        return StartGameMessage(), offset


@dataclass
class GameStateMessage(TypedNetworkMessage):
    MESSAGE_TYPE: ClassVar[MsgType] = MsgType.GAME_STATE

    # TODO: There should be more fields here...
    game_map: dict[Hex, Land]


class GameStateMessageCodec(NetworkCodec[GameStateMessage]):
    def __init__(self) -> None:
        self._map_codec = DictNetworkCodec(
            key_codec=HexNetworkCodec(), value_codec=LandNetworkCodec()
        )

    @override
    def pack_into(self, obj: GameStateMessage, buf: Buffer, offset: int = 0) -> int:
        return self._map_codec.pack_into(obj.game_map, buf, offset)

    @override
    def unpack_from(self, buf: Buffer, offset: int = 0) -> tuple[GameStateMessage, int]:
        game_map, offset_delta = self._map_codec.unpack_from(buf, offset)
        return GameStateMessage(game_map=game_map), offset_delta


_CODEC_BY_MSG_TYPE = {
    MsgType.GREETINGS: GreetingsMessageCodec(),
    MsgType.REGISTRATION: RegistrationMessageCodec(),
    MsgType.START_GAME: StartGameMessageCodec(),
    MsgType.GAME_STATE: GameStateMessageCodec(),
}


def pack_network_message_into(
    obj: TypedNetworkMessage, buf: Buffer, offset: int = 0
) -> int:
    # TODO: Figure out some better typing?
    return _CODEC_BY_MSG_TYPE[obj.MESSAGE_TYPE].pack_into(cast(Any, obj), buf, offset)
