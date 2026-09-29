from enum import StrEnum


class DeviceType(StrEnum):
    MAC = "mac"
    IPHONE = "iphone"
    WINDOWS = "windows"
    LINUX = "linux"
    SERVER = "server"
    BROWSER = "browser"


class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
