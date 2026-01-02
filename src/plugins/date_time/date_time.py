import os
from utils.app_utils import resolve_path, get_font
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageColor, ImageDraw, ImageFont
# from io import BytesIO
import logging
# import numpy as np
# import math
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

DATE_TIME_LAYOUTS = [
    {
        "name": "Day / Date / Time",
        "primary_color": "#ffffff",
        "secondary_color": "#000000",
        "icon": "layouts/ddt.png"
    }
]

DEFAULT_TIMEZONE = "Australia/Adelaide"
DEFAULT_DATE_TIME_LAYOUT = "Day / Date / Time"

class DateTime(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['date_time_layouts'] = DATE_TIME_LAYOUTS
        return template_params

    def generate_image(self, settings, device_config):
        date_time_layout = settings.get('selectDateTimeLayout')
        primary_color = ImageColor.getcolor(settings.get('primaryColor') or (255,255,255), "RGB")
        secondary_color = ImageColor.getcolor(settings.get('secondaryColor') or (0,0,0), "RGB")
        if not date_time_layout or date_time_layout not in [layout['name'] for layout in DATE_TIME_LAYOUTS]:
            date_time_layout = DEFAULT_DATE_TIME_LAYOUT

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone_name = device_config.get_config("timezone") or DEFAULT_TIMEZONE
        tz = pytz.timezone(timezone_name)
        current_time = datetime.now(tz)

        img = None
        try:
            if date_time_layout == "Day / Date / Time":
                img = self.draw_digital_clock(dimensions, current_time, primary_color, secondary_color)
            # elif date_time_layout == "Divided Clock":
            #     img = self.draw_divided_clock(dimensions, current_time, primary_color, secondary_color)
        except Exception as e:
            logger.error(f"Failed to draw clock image: {str(e)}")
            raise RuntimeError("Failed to display clock.")
        return img

    def draw_digital_clock(self, dimensions, time, primary_color=(255,255,255), secondary_color=(0,0,0)):
        w,h = dimensions
        day_str = DateTime.format_day(time)
        date_str = DateTime.format_date(time)
        time_str = DateTime.format_time(time)

        image = Image.new("RGBA", dimensions, secondary_color+(255,))
        text = Image.new("RGBA", dimensions, (0, 0, 0, 0))

        text_draw = ImageDraw.Draw(text)

        # day text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors)
        fnt = DateTime.font_that_fits("DS-Digital", day_str, w, h/3)
        text_draw.text((w/2, (h/3)*0), day_str, font=fnt, anchor="ma", fill=primary_color +(255,))

        # date text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors)
        fnt = DateTime.font_that_fits("DS-Digital", date_str, w, h/3)
        text_draw.text((w/2, (h/3)*1), date_str, font=fnt, anchor="ma", fill=primary_color +(255,))

        # time text
        # anchor horizontal-vertical hv = mm = middle,middle (https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors)
        fnt = DateTime.font_that_fits("DS-Digital", time_str, w, h/3)
        text_draw.text((w/2, (h/3)*2), time_str, font=fnt, anchor="ma", fill=primary_color +(255,))

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

    @staticmethod
    def format_day(datetime):
        return datetime.strftime('%a')

    @staticmethod
    def format_date(datetime):
        return datetime.strftime('%d %b %Y') # ('%a %d %b %Y')

    @staticmethod
    def format_time(datetime):
        return datetime.strftime('%H:%M')
