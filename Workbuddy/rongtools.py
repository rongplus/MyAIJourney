"""Weather query tool — uses the free Open-Meteo API (no API Key required)"""
from asyncio.log import logger
import os
from pathlib import Path
import subprocess
import sys
import requests
from langchain_core.tools import tool

try:
    from .ronglog import log
except ImportError:
    from ronglog import log

# The project root directory is fixed next to the current Workbuddy module,
# to avoid changing with the startup directory.
PROJECT_ROOT = Path(__file__).resolve().parent / "game_project"

def ensure_project_root():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)


def get_weather(city: str) -> str:
    """get_weather

    Query the current weather for a specified city, including temperature, humidity, weather condition, and wind speed.

    Args:
        city: City name (Chinese or English), e.g. "Beijing", "Shanghai", "Tokyo"
    """
    try:
        log(f"Querying weather for city: {city}")
        # 1. Geocoding: city name -> lat/lon
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en"},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json().get("results", [])
        if not geo_data:
            return f"City '{city}' not found. Please check the city name."

        loc = geo_data[0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)

        # 2. Weather query
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

        weather_desc = _WMO_CODES.get(code, "unknown")

        return (f"{city_name}: {weather_desc}, {temp}C, "
                f"humidity {humidity}%, wind speed {wind} m/s")
    except requests.RequestException as e:
        return f"Weather query failed: {e}"


# WMO Weather interpretation codes
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Light drizzle", 55: "Moderate drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Slight snowfall", 73: "Slight snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}


@tool
def safe_path(filepath: str) -> Path:
    """safe_path

    Prevent the Agent from accessing files outside the project directory.
    """
    log("Starting safe_path...")
    ensure_project_root()

    full_path = (PROJECT_ROOT / filepath).resolve()

    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path outside project root")

    return full_path

@tool
def read_file(filepath: str) -> str:
    """read_file

    Read a project file.

    Args:
        filepath: Relative path, e.g.:
            index.html
            js/player.js

    Returns:
        File content
    """
    log("Starting read_file...")
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

    Write to a project file.

    Args:
        filepath: Relative path
        content: File content

    Returns:
        Execution result
    """
    log("Starting write_file...")
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
    
    List files in the project directory.

    Args:
        subdir: Subdirectory

    Returns:
        File tree
    """
    log("Starting list_files...")
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


@tool
def run_python(code: str) -> str:
    """Execute a snippet of Python code in the project directory and return the output."""
    log("Starting run_python...")
    ensure_project_root()
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        if len(output) > 12000:
            output = output[-12000:]
        status = "success" if result.returncode == 0 else f"failed (exit code {result.returncode})"
        return f"{status}\n{output}" if output else status
    except subprocess.TimeoutExpired:
        return "failed: Python execution timed out after 30 seconds"
    except Exception as e:
        return f"failed: {e}"



TOOLS= [
    
    safe_path,
    read_file,
    write_file,
    list_files,
    run_python,
]
