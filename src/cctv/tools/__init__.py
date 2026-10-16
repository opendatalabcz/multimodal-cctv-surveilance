from __future__ import annotations

from cctv.tools.get_camera import GET_CAMERA_IMAGE_TOOL, execute_get_camera_image
from cctv.tools.list_cameras import LIST_CAMERAS_TOOL, execute_list_cameras
from cctv.tools.maps import (
    REVERSE_GEOCODE_TOOL,
    SEARCH_MAP_TOOL,
    execute_reverse_geocode,
    execute_search_map,
)
from cctv.tools.submit_answer import SUBMIT_ANSWER_TOOL
from cctv.tools.registry import register_tool
from cctv.tools.weather import GET_WEATHER_TOOL, execute_get_weather
from cctv.tools.web_search import WEB_SEARCH_TOOL, execute_web_search


register_tool(LIST_CAMERAS_TOOL, execute_list_cameras)
register_tool(GET_CAMERA_IMAGE_TOOL, execute_get_camera_image)
register_tool(SUBMIT_ANSWER_TOOL)
register_tool(WEB_SEARCH_TOOL, execute_web_search)
register_tool(GET_WEATHER_TOOL, execute_get_weather)
register_tool(SEARCH_MAP_TOOL, execute_search_map)
register_tool(REVERSE_GEOCODE_TOOL, execute_reverse_geocode)
