"""天气查询工具 — 使用 Open-Meteo 免费 API（无需 API Key）"""
from asyncio.log import logger
import os
from pathlib import Path
import requests
from langchain_core.tools import tool

from ronglog  import log

# 项目根目录
PROJECT_ROOT = Path("./game_project").resolve()

def ensure_project_root():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)


def get_weather(city: str) -> str:
    """get_weather

    查询指定城市的当前天气情况，包括温度、湿度、天气状况和风速。

    Args:
        city: 城市名称（中英文均可），如 "北京"、"上海"、"Tokyo"
    """
    try:
        log(f"正在查询天气 for city: {city}")
        # 1. 地理编码：城市名 -> 经纬度
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json().get("results", [])
        if not geo_data:
            return f"未找到城市「{city}」，请检查城市名称。"

        loc = geo_data[0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)

        # 2. 天气查询
        weather_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
            timeout=10,
        )
        weather_resp.raise_for_status()
        current = weather_resp.json().get("current", {})

        temp = current.get("temperature_2m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", 0)

        weather_desc = _WMO_CODES.get(code, "未知")

        return (f"{city_name}: {weather_desc}, {temp}°C, "
                f"湿度 {humidity}%, 风速 {wind} m/s")
    except requests.RequestException as e:
        return f"天气查询失败：{e}"


# WMO Weather interpretation codes
_WMO_CODES = {
    0: "晴", 1: "晴", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "小雨", 53: "小雨", 55: "中雨",
    56: "冻雨", 57: "冻雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "小雪", 75: "大雪",
    77: "霰",
    80: "阵雨", 81: "阵雨", 82: "暴雨",
    85: "阵雪", 86: "阵雪",
    95: "雷暴", 96: "雷暴", 99: "雷暴",
}


@tool
def safe_path(filepath: str) -> Path:
    """safe_path

    防止Agent访问项目目录之外的文件
    """
    log("正在启动safe_path...")
    ensure_project_root()

    full_path = (PROJECT_ROOT / filepath).resolve()

    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path outside project root")

    return full_path

@tool
def read_file(filepath: str) -> str:
    """read_file

    读取项目文件

    Args:
        filepath: 相对路径，例如:
            index.html
            js/player.js

    Returns:
        文件内容
    """
    log("正在启动read_file...")
    try:
        path = safe_path.invoke({"filepath": filepath})

        if not path.exists():
            return f"File not found: {filepath}"

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    except Exception as e:
        return f"Error reading file: {e}"

@tool
def write_file(filepath: str, content: str) -> str:
    """write_file

    写入项目文件

    Args:
        filepath: 相对路径
        content: 文件内容

    Returns:
        执行结果
    """
    log("正在启动write_file...")
    log(f"[TOOL]Writing {filepath}")
    log(f"Content length: {len(content)}")

    try:
        path = safe_path.invoke({"filepath": filepath})

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully wrote file: {filepath}"

    except Exception as e:
        return f"Error writing file: {e}"

@tool
def list_files(subdir: str = "") -> str:
    """list_files
    
    列出项目目录文件

    Args:
        subdir: 子目录

    Returns:
        文件树
    """
    log("正在启动list_files...")
    try:
        root = safe_path.invoke({"filepath": subdir})

        if not root.exists():
            return "Directory does not exist"

        results = []

        for current_root, dirs, files in os.walk(root):

            rel_root = os.path.relpath(current_root, PROJECT_ROOT)

            for file in files:
                results.append(
                    os.path.join(rel_root, file)
                )

        if not results:
            return "No files found"

        return "\n".join(sorted(results))

    except Exception as e:
        return f"Error listing files: {e}"



TOOLS= [
    
    safe_path,
    read_file,
    write_file,
    list_files
]