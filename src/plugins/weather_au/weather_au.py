from utils.app_utils import resolve_path, get_font
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageColor, ImageDraw, ImageFont
import logging
import pytz

from datetime import datetime
from .weather_bom_au_api import Location

logger = logging.getLogger(__name__)

WEATHER_AU_SETTINGS = {
        "primary_color": "#ffffff",
        "secondary_color": "#000000"
    }

DEFAULT_TIMEZONE = "Australia/Adelaide"

class WeatherAU(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['weather_au'] = WEATHER_AU_SETTINGS
        return template_params

    def generate_image(self, settings, device_config):
        latitude = float(settings.get('latitude'))
        longitude = float(settings.get('longitude'))
        if not latitude or not longitude:
            raise RuntimeError("Latitude and Longitude are required.")

        primary_color = ImageColor.getcolor(settings.get('primaryColor') or (255,255,255), "RGB")
        secondary_color = ImageColor.getcolor(settings.get('secondaryColor') or (0,0,0), "RGB")

        # display_rain = settings.get('displayRain') == "true"
        # moon_phase = settings.get('moonPhase') == "true"

        # locationSearchStr = "Adelaide Airport"
        # latitude = -34.942961651637376
        # longitude = 138.50103378295898

        # results = Location.search(locationSearchStr)
        # logger.info(f"Locations matching search string [{locationSearchStr}]: {results}")

        results = Location.search(latitude, longitude)
        locationSearchStr = f"{latitude:.4f},{longitude:.4f}"
        logger.info(f"Locations matching search lat,lon [{latitude},{longitude}]: {results}")

        if len(results) == 0:
            raise RuntimeError(f"No location found for search string: {locationSearchStr}")
        location = results[0]
        logger.info(f"Selected location: {location}")

        # location_details = location.details()
        # logger.info(f"details: {location_details}")
        #
        # timezone_name = location_details.timezone #device_config.get_config("timezone") or DEFAULT_TIMEZONE
        # tz = pytz.timezone(timezone_name)
        # current_time = datetime.now(tz)

        observations = location.observations()
        logger.info(f"observations: {observations}")

        # warnings = location.warnings()
        # logger.info(f"warnings: {warnings}")
        # if len(warnings) > 0:
        #     warningtime = warnings[0].issue_time
        #     logger.info(f"warningtime: {warningtime} = , time local = {warningtime.astimezone(tz)}")
        #
        # forcast_daily = location.forcast_daily()
        # logger.info(f"forcast_daily: {len(forcast_daily)}")
        #
        # forcast_hourly = location.forcast_hourly()
        # logger.info(f"forcast_hourly: {len(forcast_hourly)}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        # img = None
        try:
            img = self.draw_weather(observations, dimensions, primary_color, secondary_color) # , primary_color, secondary_color
        except Exception as e:
            logger.error(f"Failed to draw clock image: {str(e)}")
            raise RuntimeError("Failed to display clock.")
        return img

    def draw_weather(self, observations, dimensions, primary_color=(255,255,255), secondary_color=(0,0,0)) -> Image:
        w,h = dimensions

        temp_str = f"NOW: {observations.temp} C"
        max_min_str = f"MAX: {observations.max_temp.value} C, MIN: {observations.min_temp.value} C"
        wind_rain_str = f"WIND: {observations.wind.speed_knot} KN / RAIN: {observations.rain_since_9am} mm"
        # max_leng_text = max([temp_str, max_min_str, wind_rain_str])
        # logger.info(f"max_leng_text = {max_leng_text}")

        image = Image.new("RGBA", dimensions, secondary_color+(255,))
        text = Image.new("RGBA", dimensions, (0, 0, 0, 0))

        text_draw = ImageDraw.Draw(text)

        # temp_str text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors
        fnt = WeatherAU.font_that_fits("DS-Digital", temp_str, w, h/3)
        text_draw.text((w/2, (h/3)*0), temp_str, font=fnt, anchor="ma", fill=primary_color +(255,))

        # max_min_str text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors)
        fnt = WeatherAU.font_that_fits("DS-Digital", max_min_str, w, h/3)
        text_draw.text((w/2, (h/3)*1), max_min_str, font=fnt, anchor="ma", fill=primary_color +(255,))

        # wind_rain_str text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors)
        fnt = WeatherAU.font_that_fits("DS-Digital", wind_rain_str, w, h/3)
        text_draw.text((w/2, (h/3)*2), wind_rain_str, font=fnt, anchor="ma", fill=primary_color +(255,))

        combined = Image.alpha_composite(image, text)

        return combined

    @staticmethod
    def font_that_fits(font_name, text, width, height):
        font_size = height
        fnt = get_font(font_name, font_size)
        # logger.info(f"Initial font_size = {font_size}")

        padding = 2
        text_length = fnt.getlength(text)
        bb = fnt.getbbox(text)
        # logger.info(f"textlength = {text_length}, font_name = {font_name}, font_size = {font_size}, bounding box = {bb}, text = {text}, drawing size = {width} x {height}")

        if text_length + (padding * 2) > width:
            while text_length + (padding * 2) > width:
                if font_size <= 2:
                    break
                font_size = font_size - 1
                fnt = get_font(font_name, font_size)
                text_length = fnt.getlength(text)

            # logger.info(f"Adjusted font to fit better: font_size = {font_size}")

        return fnt
