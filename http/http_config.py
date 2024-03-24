# socket 相关buffer 配置
import enum


buffer = {
    "read_buffer_size": 2048,
    "write_buffer_size": 1024
}
# http 支持的方法集合
class METHOD(enum.Enum):
    GET = enum.auto()
    POST = enum.auto()
    HEAD = enum.auto()
    PUT = enum.auto()
    DELETE = enum.auto()
    TRACE = enum.auto()
    OPTIONS = enum.auto()
    CONNECT = enum.auto()
    PATH = enum.auto()

# 主状态机状态
class CHECK_STATE(enum.Enum):
    CHECK_STATE_REQUESTLINE = enum.auto()
    CHECK_STATE_HEADER = enum.auto()
    CHECK_STATE_CONTENT = enum.auto()

# 从状态机状态
class LINE_STATUS(enum.Enum):
    LINE_OK = enum.auto()
    LINE_BAD = enum.auto()
    LINE_OPEN = enum.auto()

# http 请求处理结果码
class HTTP_CODE(enum.Enum):
    NO_REQUEST = enum.auto()
    GET_REQUEST = enum.auto()
    BAD_REQUEST = enum.auto()
    NO_RESOURCE = enum.auto()
    FORBIDDEN_REQUEST = enum.auto()
    FILE_REQUEST = enum.auto()
    INTERNAL_ERROR = enum.auto()
    CLOSED_CONNECTION = enum.auto()

# http 响应信息
response_message = {
    "ok_200_title": "OK",
    "error_400_title": "Bad Request",
    "error_400_form": "Your request has bad syntax or is inherently impossible to staisfy.\n",
    "error_403_title": "Forbidden",
    "error_403_form": "You do not have permission to get file form this server.\n",
    "error_404_title": "Not Found",
    "error_404_form": "The requested file was not found on this server.\n",
    "error_500_title": "Internal Error",
    "error_500_form": "There was an unusual problem serving the request file.\n",
}
