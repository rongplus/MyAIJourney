"""天气查询工具 — 使用 Open-Meteo 免费 API（无需 API Key）"""
import requests
from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """查询指定城市的当前天气情况，包括温度、湿度、天气状况和风速。

    Args:
        city: 城市名称（中英文均可），如 "北京"、"上海"、"Tokyo"
    """
    try:
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

# 工具列表
TOOLS = [get_weather]
