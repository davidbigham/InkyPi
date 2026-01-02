from typing import Optional

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import os
import requests
import logging
from datetime import datetime, timedelta, timezone, date
from astral import moon
import pytz
from io import BytesIO
import math
from ..weather_au.weather_bom_au_api import Location
logger = logging.getLogger(__name__)

def get_moon_phase_name(phase_age: float) -> str:
    """Determines the name of the lunar phase based on the age of the moon."""
    PHASES_THRESHOLDS = [
        (1.0, "newmoon"),
        (7.0, "waxingcrescent"),
        (8.5, "firstquarter"),
        (14.0, "waxinggibbous"),
        (15.5, "fullmoon"),
        (22.0, "waninggibbous"),
        (23.5, "lastquarter"),
        (29.0, "waningcrescent"),
    ]

    for threshold, phase_name in PHASES_THRESHOLDS:
        if phase_age <= threshold:
            return phase_name
    return "newmoon"

UNITS = {
    "standard": {
        "temperature": "K",
        "speed": "m/s"
    },
    "metric": {
        "temperature": "°C",
        "speed": "m/s"

    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph"
    }
}

WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={long}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={long}&appid={api_key}"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={long}&hourly=temperature_2m,precipitation,precipitation_probability,relative_humidity_2m,surface_pressure,visibility&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset&current_weather=true&timezone=auto&models=best_match&forecast_days={forecast_days}"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={long}&hourly=european_aqi,uv_index,uv_index_clear_sky&timezone=auto"
OPEN_METEO_UNIT_PARAMS = {
    "standard": "temperature_unit=kelvin&wind_speed_unit=ms&precipitation_unit=mm",
    "metric":   "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "imperial": "temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
}

class Weather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap",
            "expected_key": "OPEN_WEATHER_MAP_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        lat = float(settings.get('latitude'))
        long = float(settings.get('longitude'))
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        weather_provider = settings.get('weatherProvider', 'OpenWeatherMap')
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        try:
            if weather_provider == "OpenWeatherMap":
                api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
                if not api_key:
                    raise RuntimeError("Open Weather Map API Key not configured.")
                weather_data = self.get_weather_data(api_key, units, lat, long)
                aqi_data = self.get_air_quality(api_key, lat, long)
                if settings.get('titleSelection', 'location') == 'location':
                    title = self.get_location(api_key, lat, long)
                if settings.get('weatherTimeZone', 'locationTimeZone') == 'locationTimeZone':
                    logger.info("Using location timezone for OpenWeatherMap data.")
                    wtz = self.parse_timezone(weather_data)
                    template_params = self.parse_weather_data(weather_data, aqi_data, wtz, units, time_format, lat)
                else:
                    logger.info("Using configured timezone for OpenWeatherMap data.")
                    template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format, lat)
            elif weather_provider == "OpenMeteo":
                forecast_days = 7
                weather_data = self.get_open_meteo_data(lat, long, units, forecast_days + 1)
                aqi_data = self.get_open_meteo_air_quality(lat, long)
                template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format, lat)
            elif weather_provider == "BomAU":
                locations = Location.search(lat, long)
                if len(locations) <= 0:
                    raise RuntimeError(f"BOM AU Location not found for {lat:.4f}, {long:.4f}")
                location = locations[0]
                units = 'metric'
                if settings.get('titleSelection', 'location') == 'location':
                    title = location.name
                template_params = self.get_bom_au_template_params(location, units, time_format, lat, long)
                # bomTz = weather_data["details"].timezone
                # tz = pytz.timezone(bomTz)
                # aqi_data = None # or use OpenMeteo? self.get_open_meteo_air_quality(lat, long)
                # template_params = self.parse_bom_au_data(weather_data, aqi_data, tz, units, time_format, lat)
            else:
                raise RuntimeError(f"Unknown weather provider: {weather_provider}")

            template_params['title'] = title
        except Exception as e:
            logger.error(f"{weather_provider} request failed: {str(e)}")
            raise RuntimeError(f"{weather_provider} request failure, please check logs.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params["plugin_settings"] = settings

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "weather.html", "weather.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def parse_weather_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current")
        dt = datetime.fromtimestamp(current.get('dt'), tz=timezone.utc).astimezone(tz)
        current_icon = current.get("weather")[0].get("icon")
        icon_codes_to_preserve = ["01", "02", "10"]
        icon_code = current_icon[:2]
        current_suffix = current_icon[-1]

        if icon_code not in icon_codes_to_preserve:
            if current_icon.endswith('n'):
                current_icon = current_icon.replace("n", "d")
        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temp"))),
            "feels_like": str(round(current.get("feels_like"))),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }
        data['forecast'] = self.parse_forecast(weather_data.get('daily'), tz, current_suffix, lat)
        data['data_points'] = self.parse_data_points(weather_data, aqi_data, tz, units, time_format)

        data['hourly_forecast'] = self.parse_hourly(weather_data.get('hourly'), tz, time_format, units)
        return data

    def parse_open_meteo_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current_weather", {})
        dt = datetime.fromisoformat(current.get('time')).astimezone(tz) if current.get('time') else datetime.now(tz)
        weather_code = current.get("weathercode", 0)
        is_day = current.get("is_day", 1)
        current_icon = self.map_weather_code_to_icon(weather_code, is_day)

        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temperature", 0))),
            "feels_like": str(round(current.get("apparent_temperature", current.get("temperature", 0)))),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_open_meteo_forecast(weather_data.get('daily', {}), tz, is_day, lat)
        data['data_points'] = self.parse_open_meteo_data_points(weather_data, aqi_data, tz, units, time_format)

        data['hourly_forecast'] = self.parse_open_meteo_hourly(weather_data.get('hourly', {}), tz, time_format)
        return data

    def map_weather_code_to_icon(self, weather_code, is_day):

        icon = "01d" # Default to clear day icon

        if weather_code in [0]:   # Clear sky
            icon = "01d"
        elif weather_code in [1]: # Mainly clear
            icon = "022d"
        elif weather_code in [2]: # Partly cloudy
            icon = "02d"
        elif weather_code in [3]: # Overcast
            icon = "04d"
        elif weather_code in [51, 61, 80]: # Drizzle, showers, rain: Light
            icon = "51d"
        elif weather_code in [53, 63, 81]: # Drizzle, showers, rain: Moderatr
            icon = "53d"
        elif weather_code in [55, 65, 82]: # Drizzle, showers, rain: Heavy
            icon = "09d"
        elif weather_code in [45]: # Fog
            icon = "50d"
        elif weather_code in [48]: # Icy fog
            icon = "48d"
        elif weather_code in [56, 66]: # Light freezing Drizzle
            icon = "56d"
        elif weather_code in [57, 67]: # Freezing Drizzle
            icon = "57d"
        elif weather_code in [71, 85]: # Snow fall: Slight
            icon = "71d"
        elif weather_code in [73]:     # Snow fall: Moderate
            icon = "73d"
        elif weather_code in [75, 86]: # Snow fall: Heavy
            icon = "13d"
        elif weather_code in [77]:     # Snow grain
            icon = "77d"
        elif weather_code in [95]: # Thunderstorm
            icon = "11d"
        elif weather_code in [96, 99]: # Thunderstorm with slight and heavy hail
            icon = "11d"

        if is_day == 0:
            if icon == "01d":
                icon = "01n"      # Clear sky night
            elif icon == "022d":
                icon = "022n"     # Mainly clear night
            elif icon == "02d":
                icon = "02n"      # Partly cloudy night
            elif icon == "10d":
                icon = "10n"      # Rain night

        return icon

    def get_moon_phase_icon_path(self, phase_name: str, lat: float) -> str:
        """Determines the path to the moon icon, inverting it if the location is in the Southern Hemisphere."""
        # Waxing, Waning, First and Last quarter phases are inverted between hemispheres.
        if lat < 0: # Southern Hemisphere
            if phase_name == "waxingcrescent":
                phase_name = "waningcrescent"
            elif phase_name == "waxinggibbous":
                phase_name = "waninggibbous"
            elif phase_name == "waningcrescent":
                phase_name = "waxingcrescent"
            elif phase_name == "waninggibbous":
                phase_name = "waxinggibbous"
            elif phase_name == "firstquarter":
                phase_name = "lastquarter"
            elif phase_name == "lastquarter":
                phase_name = "firstquarter"

        return self.get_plugin_dir(f"icons/{phase_name}.png")

    def parse_forecast(self, daily_forecast, tz, current_suffix, lat):
        """
        - daily_forecast: list of daily entries from One‑Call v3 (each has 'dt', 'weather', 'temp', 'moon_phase')
        - tz: your target tzinfo (e.g. from zoneinfo or pytz)
        """
        PHASES = [
            (0.0, "newmoon"),
            (0.25, "firstquarter"),
            (0.5, "fullmoon"),
            (0.75, "lastquarter"),
            (1.0, "newmoon"),
        ]

        def choose_phase_name(phase: float) -> str:
            for target, name in PHASES:
                if math.isclose(phase, target, abs_tol=1e-3):
                    return name
            if 0.0 < phase < 0.25:
                return "waxingcrescent"
            elif 0.25 < phase < 0.5:
                return "waxinggibbous"
            elif 0.5 < phase < 0.75:
                return "waninggibbous"
            else:
                return "waningcrescent"

        forecast = []
        icon_codes_to_apply_current_suffix = ["01", "02", "10"]
        for day in daily_forecast:
            # --- weather icon ---
            weather_icon = day["weather"][0]["icon"]  # e.g. "10d", "01n"
            icon_code = weather_icon[:2]
            if icon_code in icon_codes_to_apply_current_suffix:
                weather_icon_base = weather_icon[:-1]
                weather_icon = weather_icon_base + current_suffix
            else:
                if weather_icon.endswith('n'):
                    weather_icon = weather_icon.replace("n", "d")
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            # --- moon phase & icon ---
            moon_phase = float(day["moon_phase"])  # [0.0–1.0]
            phase_name_north_hemi = choose_phase_name(moon_phase)
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)
            # --- true illumination percent, no decimals ---
            illum_fraction = (1 - math.cos(2 * math.pi * moon_phase)) / 2
            moon_pct = f"{illum_fraction * 100:.0f}"

            # --- date & temps ---
            dt = datetime.fromtimestamp(day["dt"], tz=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")

            forecast.append(
                {
                    "day": day_label,
                    "high": int(day["temp"]["max"]),
                    "low": int(day["temp"]["min"]),
                    "icon": weather_icon_path,
                    "moon_phase_pct": moon_pct,
                    "moon_phase_icon": moon_icon_path,
                }
            )

        return forecast

    def parse_open_meteo_forecast(self, daily_data, tz, is_day, lat):
        """
        Parse the daily forecast from Open-Meteo API and calculate moon phase and illumination using the local 'astral' library.
        """
        times = daily_data.get('time', [])
        weather_codes = daily_data.get('weathercode', [])
        temp_max = daily_data.get('temperature_2m_max', [])
        temp_min = daily_data.get('temperature_2m_min', [])

        forecast = []

        for i in range(0, len(times)):
            dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")

            code = weather_codes[i] if i < len(weather_codes) else 0
            weather_icon = self.map_weather_code_to_icon(code, is_day)
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            timestamp = int(dt.replace(hour=12, minute=0, second=0).timestamp())
            target_date: date = dt.date() + timedelta(days=1)

            try:
                phase_age = moon.phase(target_date)
                phase_name_north_hemi = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception as e:
                logger.error(f"Error calculating moon phase for {target_date}: {e}")
                illum_pct = 0
                phase_name = "newmoon"
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)

            forecast.append({
                "day": day_label,
                "high": int(temp_max[i]) if i < len(temp_max) else 0,
                "low": int(temp_min[i]) if i < len(temp_min) else 0,
                "icon": weather_icon_path,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path
            })

        return forecast

    def parse_hourly(self, hourly_forecast, tz, time_format, units):
        hourly = []
        for hour in hourly_forecast[:24]:
            dt = datetime.fromtimestamp(hour.get('dt'), tz=timezone.utc).astimezone(tz)
            rain_mm = hour.get("rain", {}).get("1h", 0.0)
            if units == "imperial":
                rain = rain_mm / 25.4
            else:
                rain = rain_mm
            hour_forecast = {
                "time": self.format_time(dt, time_format, hour_only=True),
                "temperature": int(hour.get("temp")),
                "precipitation": hour.get("pop"),
                "rain": round(rain, 2)
            }
            hourly.append(hour_forecast)
        return hourly

    def parse_open_meteo_hourly(self, hourly_data, tz, time_format):
        hourly = []
        times = hourly_data.get('time', [])
        temperatures = hourly_data.get('temperature_2m', [])
        precipitation_probabilities = hourly_data.get('precipitation_probability', [])
        rain = hourly_data.get('precipitation', [])
        current_time_in_tz = datetime.now(tz)
        start_index = 0
        for i, time_str in enumerate(times):
            try:
                dt_hourly = datetime.fromisoformat(time_str).astimezone(tz)
                if dt_hourly.date() == current_time_in_tz.date() and dt_hourly.hour >= current_time_in_tz.hour:
                    start_index = i
                    break
                if dt_hourly.date() > current_time_in_tz.date():
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} in hourly data.")
                continue

        sliced_times = times[start_index:]
        sliced_temperatures = temperatures[start_index:]
        sliced_precipitation_probabilities = precipitation_probabilities[start_index:]
        sliced_rain = rain[start_index:]

        for i in range(min(24, len(sliced_times))):
            dt = datetime.fromisoformat(sliced_times[i]).astimezone(tz)
            hour_forecast = {
                "time": self.format_time(dt, time_format, True),
                "temperature": int(sliced_temperatures[i]) if i < len(sliced_temperatures) else 0,
                "precipitation": (sliced_precipitation_probabilities[i] / 100) if i < len(sliced_precipitation_probabilities) else 0,
                "rain": (sliced_rain[i]) if i < len(sliced_rain) else 0
            }
            hourly.append(hour_forecast)
        return hourly

    def parse_data_points(self, weather, air_quality, tz, units, time_format):
        data_points = []
        sunrise_epoch = weather.get('current', {}).get("sunrise")

        if sunrise_epoch:
            sunrise_dt = datetime.fromtimestamp(sunrise_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunrise.png')
            })
        else:
            logging.error(f"Sunrise not found in OpenWeatherMap response, this is expected for polar areas in midnight sun and polar night periods.")

        sunset_epoch = weather.get('current', {}).get("sunset")
        if sunset_epoch:
            sunset_dt = datetime.fromtimestamp(sunset_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunset.png')
            })
        else:
            logging.error(f"Sunset not found in OpenWeatherMap response, this is expected for polar areas in midnight sun and polar night periods.")

        wind_deg = weather.get('current', {}).get("wind_deg", 0)
        wind_arrow = self.get_wind_arrow(wind_deg)
        data_points.append({
            "label": "Wind",
            "measurement": weather.get('current', {}).get("wind_speed"),
            "unit": UNITS[units]["speed"],
            "icon": self.get_plugin_dir('icons/wind.png'),
            "arrow": wind_arrow
        })

        data_points.append({
            "label": "Humidity",
            "measurement": weather.get('current', {}).get("humidity"),
            "unit": '%',
            "icon": self.get_plugin_dir('icons/humidity.png')
        })

        data_points.append({
            "label": "Pressure",
            "measurement": weather.get('current', {}).get("pressure"),
            "unit": 'hPa',
            "icon": self.get_plugin_dir('icons/pressure.png')
        })

        data_points.append({
            "label": "UV Index",
            "measurement": weather.get('current', {}).get("uvi"),
            "unit": '',
            "icon": self.get_plugin_dir('icons/uvi.png')
        })

        visibility = weather.get('current', {}).get("visibility")/1000
        visibility_str = f">{visibility}" if visibility >= 10 else visibility
        data_points.append({
            "label": "Visibility",
            "measurement": visibility_str,
            "unit": 'km',
            "icon": self.get_plugin_dir('icons/visibility.png')
        })

        aqi = air_quality.get('list', [])[0].get("main", {}).get("aqi")
        data_points.append({
            "label": "Air Quality",
            "measurement": aqi,
            "unit": ["Good", "Fair", "Moderate", "Poor", "Very Poor"][int(aqi)-1],
            "icon": self.get_plugin_dir('icons/aqi.png')
        })

        return data_points

    def parse_open_meteo_data_points(self, weather_data, aqi_data, tz, units, time_format):
        """Parses current data points from Open-Meteo API response."""
        data_points = []
        daily_data = weather_data.get('daily', {})
        current_data = weather_data.get('current_weather', {})
        hourly_data = weather_data.get('hourly', {})

        current_time = datetime.now(tz)

        # Sunrise
        sunrise_times = daily_data.get('sunrise', [])
        if sunrise_times:
            sunrise_dt = datetime.fromisoformat(sunrise_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunrise.png')
            })
        else:
            logging.error(f"Sunrise not found in Open-Meteo response, this is expected for polar areas in midnight sun and polar night periods.")

        # Sunset
        sunset_times = daily_data.get('sunset', [])
        if sunset_times:
            sunset_dt = datetime.fromisoformat(sunset_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunset.png')
            })
        else:
            logging.error(f"Sunset not found in Open-Meteo response, this is expected for polar areas in midnight sun and polar night periods.")

        # Wind
        wind_speed = current_data.get("windspeed", 0)
        wind_deg = current_data.get("winddirection", 0)
        wind_arrow = self.get_wind_arrow(wind_deg)
        wind_unit = UNITS[units]["speed"]
        data_points.append({
            "label": "Wind", "measurement": wind_speed, "unit": wind_unit,
            "icon": self.get_plugin_dir('icons/wind.png'), "arrow": wind_arrow
        })

        # Humidity
        current_humidity = "N/A"
        humidity_hourly_times = hourly_data.get('time', [])
        humidity_values = hourly_data.get('relative_humidity_2m', [])
        for i, time_str in enumerate(humidity_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_humidity = int(humidity_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for humidity.")
                continue
        data_points.append({
            "label": "Humidity", "measurement": current_humidity, "unit": '%',
            "icon": self.get_plugin_dir('icons/humidity.png')
        })

        # Pressure
        current_pressure = "N/A"
        pressure_hourly_times = hourly_data.get('time', [])
        pressure_values = hourly_data.get('surface_pressure', [])
        for i, time_str in enumerate(pressure_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_pressure = int(pressure_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for pressure.")
                continue
        data_points.append({
            "label": "Pressure", "measurement": current_pressure, "unit": 'hPa',
            "icon": self.get_plugin_dir('icons/pressure.png')
        })

        # UV Index
        uv_index_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        uv_index_values = aqi_data.get('hourly', {}).get('uv_index', [])
        current_uv_index = "N/A"
        for i, time_str in enumerate(uv_index_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_uv_index = uv_index_values[i]
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for UV Index.")
                continue
        data_points.append({
            "label": "UV Index", "measurement": current_uv_index, "unit": '',
            "icon": self.get_plugin_dir('icons/uvi.png')
        })

        # Visibility
        current_visibility = "N/A"
        visibility_hourly_times = hourly_data.get('time', [])
        visibility_values = hourly_data.get('visibility', [])
        for i, time_str in enumerate(visibility_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    visibility = visibility_values[i]
                    if units == "imperial":
                        current_visibility = int(round(visibility, 0))
                        unit_label = "ft"
                    else:
                        current_visibility = round(visibility / 1000, 1)
                        unit_label = "km"
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for visibility.")
                continue

        visibility_str = f">{current_visibility}" if isinstance(current_visibility, (int, float)) and (
            (units == "imperial" and current_visibility >= 32808) or
            (units != "imperial" and current_visibility >= 10)
        ) else current_visibility

        data_points.append({
            "label": "Visibility", "measurement": visibility_str, "unit": unit_label,
            "icon": self.get_plugin_dir('icons/visibility.png')
        })

        # Air Quality
        aqi_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        aqi_values = aqi_data.get('hourly', {}).get('european_aqi', [])
        current_aqi = "N/A"
        for i, time_str in enumerate(aqi_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_aqi = round(aqi_values[i], 1)
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for AQI.")
                continue
        scale = ""
        if current_aqi:
            scale = ["Good","Fair","Moderate","Poor","Very Poor","Ext Poor"][min(current_aqi//20,5)]
        data_points.append({
            "label": "Air Quality", "measurement": current_aqi,
            "unit": scale, "icon": self.get_plugin_dir('icons/aqi.png')
        })

        return data_points

    def get_wind_arrow(self, wind_deg: float) -> str:
        DIRECTIONS = [
            ("↓", 22.5),    # North (N)
            ("↙", 67.5),    # North-East (NE)
            ("←", 112.5),   # East (E)
            ("↖", 157.5),   # South-East (SE)
            ("↑", 202.5),   # South (S)
            ("↗", 247.5),   # South-West (SW)
            ("→", 292.5),   # West (W)
            ("↘", 337.5),   # North-West (NW)
            ("↓", 360.0)    # Wrap back to North
        ]
        wind_deg = wind_deg % 360
        for arrow, upper_bound in DIRECTIONS:
            if wind_deg < upper_bound:
                return arrow

        return "↑"

    def get_weather_data(self, api_key, units, lat, long):
        url = WEATHER_URL.format(lat=lat, long=long, units=units, api_key=api_key)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to retrieve weather data: {response.content}")
            raise RuntimeError("Failed to retrieve weather data.")

        return response.json()

    def get_air_quality(self, api_key, lat, long):
        url = AIR_QUALITY_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to get air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve air quality data.")

        return response.json()

    def get_location(self, api_key, lat, long):
        url = GEOCODING_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to get location: {response.content}")
            raise RuntimeError("Failed to retrieve location.")

        location_data = response.json()[0]
        location_str = f"{location_data.get('name')}, {location_data.get('state', location_data.get('country'))}"

        return location_str

    def get_open_meteo_data(self, lat, long, units, forecast_days):
        unit_params = OPEN_METEO_UNIT_PARAMS[units]
        url = OPEN_METEO_FORECAST_URL.format(lat=lat, long=long, forecast_days=forecast_days) + f"&{unit_params}"
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to retrieve Open-Meteo weather data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo weather data.")

        return response.json()

    def get_open_meteo_air_quality(self, lat, long):
        url = OPEN_METEO_AIR_QUALITY_URL.format(lat=lat, long=long)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logging.error(f"Failed to retrieve Open-Meteo air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo air quality data.")

        return response.json()

    def format_time(self, dt, time_format, hour_only=False, include_am_pm=True):
        """Format datetime based on 12h or 24h preference"""
        if time_format == "24h":
            return dt.strftime("%H:00" if hour_only else "%H:%M")

        if include_am_pm:
            fmt = "%I %p" if hour_only else "%I:%M %p"
        else:
            fmt = "%I" if hour_only else "%I:%M"

        return dt.strftime(fmt).lstrip("0")

    def parse_timezone(self, weatherdata):
        """Parse timezone from weather data"""
        if 'timezone' in weatherdata:
            logger.info(f"Using timezone from weather data: {weatherdata['timezone']}")
            return pytz.timezone(weatherdata['timezone'])
        else:
            logger.error("Failed to retrieve Timezone from weather data")
            raise RuntimeError("Timezone not found in weather data.")

    def get_bom_au_template_params(self, location, units, time_format, lat, long):
        location_details = location.details()
        observations = location.observations()
        warnings = location.warnings()
        forcast_daily = location.forcast_daily()
        forcast_hourly = location.forcast_hourly()

        bomTz = location_details.timezone
        tz = pytz.timezone(bomTz)

        now_forcast_day = forcast_daily[0]
        for forcast_day in forcast_daily:
            if forcast_day.now is not None:
                now_forcast_day = forcast_day
                break

        now_dt = now_forcast_day.date.astimezone(tz) if now_forcast_day.date is not None else datetime.now(tz)
        icon_descriptor = now_forcast_day.icon_descriptor
        is_day = not now_forcast_day.now.is_night

        aqi_data = None # or use OpenMeteo? self.get_open_meteo_air_quality(lat, long)

        temp = observations.temp if observations.temp is not None else 0
        temp_feels_like = observations.temp_feels_like if observations.temp_feels_like is not None else temp

        current_icon = self.map_bom_au_icon_descriptor_to_icon(icon_descriptor, is_day)

        data = {
            "current_date": now_dt.strftime("%A, %B %d"),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(temp)),
            "feels_like": str(round(temp_feels_like)),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_bom_au_daily_forecast(forcast_daily, tz, is_day, lat)
        data['data_points'] = self.parse_bom_au_data_points(observations, forcast_daily, forcast_hourly, aqi_data, tz, units, time_format)

        data['hourly_forecast'] = self.parse_bom_au_hourly(forcast_hourly, tz, time_format)

        logger.info(f"BOMAu template data: {data}")
        return data

    def parse_bom_au_daily_forecast(self, forcast_daily, tz, is_day, lat):
        """
        Parse the daily forecast from BOM AU API and calculate moon phase and illumination using the local 'astral' library.
        """
        forecast = []

        for forcast_day in forcast_daily:
            dt = forcast_day.date.astimezone(tz)
            day_label = dt.strftime("%a")
            is_day = not forcast_day.now.is_night if forcast_day.now is not None else True

            icon_descriptor = forcast_day.icon_descriptor
            weather_icon = self.map_bom_au_icon_descriptor_to_icon(icon_descriptor, is_day)
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            target_date: date = dt.date() + timedelta(days=1)
            try:
                phase_age = moon.phase(target_date)
                phase_name_north_hemi = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception as e:
                logger.error(f"Error calculating moon phase for {target_date}: {e}")
                illum_pct = 0
                phase_name_north_hemi = "newmoon"
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)

            now = forcast_day.now
            now_min = Optional[float]
            now_max = Optional[float]
            if now is not None:
                temp_now = now.temp_now
                temp_later = now.temp_later
                now_min = min([temp_now, temp_later])
                now_max = max([temp_now, temp_later])

            temp_max = forcast_day.temp_max if forcast_day.temp_max is not None else now_max
            temp_min = forcast_day.temp_min if forcast_day.temp_min is not None else now_min

            forecast.append({
                "day": day_label,
                "high": int(temp_max),
                "low": int(temp_min),
                "icon": weather_icon_path,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path
            })

        logger.info(f"BOMAu daily forecast: {forecast}")
        return forecast

    def parse_bom_au_hourly(self, forcast_hourly, tz, time_format):
        """
        Parse the hourly forecast from BOM AU API
        """
        hourly = []

        current_time_in_tz = datetime.now(tz)

        for forcast_hour in forcast_hourly:
            forecast_time_in_tz = forcast_hour.time.astimezone(tz)
            if forecast_time_in_tz.date() < current_time_in_tz.date():
                continue
            if forecast_time_in_tz.date() == current_time_in_tz.date() and forecast_time_in_tz.hour < current_time_in_tz.hour:
                continue

            hour_forecast = {
                "time": self.format_time(forecast_time_in_tz, time_format, True),
                "temperature": int(forcast_hour.temp) if forcast_hour.temp else 0,
                "precipitation": (forcast_hour.rain.chance / 100) if forcast_hour.rain.chance else 0,
                "rain": (forcast_hour.rain.amount.max) if forcast_hour.rain.amount.max is not None else 0
            }
            hourly.append(hour_forecast)

        logger.info(f"BOMAu hourly forecast: {hourly}")
        return hourly

    def parse_bom_au_data_points(self, observations, forcast_daily, forcast_hourly, aqi_data, tz, units, time_format):
        """Parses current data points from BOM AU API """
        data_points = []

        current_time_in_tz = datetime.now(tz)

        now_forcast_day = forcast_daily[0]
        for forcast_day in forcast_daily:
            if forcast_day.now is not None:
                now_forcast_day = forcast_day
                break

        # Sunrise
        sunrise_time = now_forcast_day.astronomical.sunrise_time if now_forcast_day.astronomical is not None else None
        if sunrise_time:
            sunrise_dt = sunrise_time.astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunrise.png')
            })
        else:
            logging.error(f"Sunrise not found in BOM AU response, this is expected for polar areas in midnight sun and polar night periods.")

        # Sunset
        sunset_time = now_forcast_day.astronomical.sunset_time if now_forcast_day.astronomical is not None else None
        if sunset_time:
            sunset_dt = sunset_time.astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunset.png')
            })
        else:
            logging.error(f"Sunset not found in Open-Meteo response, this is expected for polar areas in midnight sun and polar night periods.")

        # Wind
        wind_speed = observations.wind.speed_knot if observations.wind is not None else 0
        wind_direction = observations.wind.direction
        wind_arrow = self.get_bom_au_wind_arrow(wind_direction)
        wind_unit = "knots"
        data_points.append({
            "label": "Wind",
            "measurement": wind_speed,
            "unit": wind_unit,
            "icon": self.get_plugin_dir('icons/wind.png'),
            "arrow": wind_arrow
        })

        # Humidity
        current_humidity = observations.humidity if observations.humidity is not None else "N/A"
        data_points.append({
            "label": "Humidity",
            "measurement": current_humidity,
            "unit": '%',
            "icon": self.get_plugin_dir('icons/humidity.png')
        })


        # Rain since 9am
        current_rainfall = observations.rain_since_9am if observations.rain_since_9am is not None else "N/A"
        data_points.append({
            "label": "Rain",
            "measurement": current_rainfall,
            "unit": 'mm',
            "icon": self.get_plugin_dir('icons/09d.png')
        })

        # # Pressure - unavailable on BOM API
        # current_pressure = "N/A"
        # data_points.append({
        #     "label": "Pressure",
        #     "measurement": current_pressure,
        #     "unit": 'hPa',
        #     "icon": self.get_plugin_dir('icons/pressure.png')
        # })

        # UV Index
        current_uv_index = now_forcast_day.uv.max_index if now_forcast_day.uv.max_index is not None else "N/A"
        data_points.append({
            "label": "UV Index",
            "measurement": current_uv_index,
            "unit": '',
            "icon": self.get_plugin_dir('icons/uvi.png')
        })

        # # Visibility - unavailable in BOM API
        # visibility_str = "N/A"
        # data_points.append({
        #     "label": "Visibility",
        #     "measurement": visibility_str,
        #     "unit": '',
        #     "icon": self.get_plugin_dir('icons/visibility.png')
        # })

        # Air Quality
        current_aqi = "N/A"
        scale = ""
        if aqi_data:
            aqi_hourly_times = aqi_data.get('hourly', {}).get('time', [])
            aqi_values = aqi_data.get('hourly', {}).get('european_aqi', [])
            for i, time_str in enumerate(aqi_hourly_times):
                try:
                    if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time_in_tz.hour:
                        current_aqi = round(aqi_values[i], 1)
                        break
                except ValueError:
                    logger.warning(f"Could not parse time string {time_str} for AQI.")
                    continue
            if current_aqi != "N/A":
                scale = ["Good","Fair","Moderate","Poor","Very Poor","Ext Poor"][min(current_aqi//20,5)]
        data_points.append({
            "label": "Air Quality",
            "measurement": current_aqi,
            "unit": scale,
            "icon": self.get_plugin_dir('icons/aqi.png')
        })

        return data_points

    def map_bom_au_icon_descriptor_to_icon(self, icon_descriptor, is_day):

        icon = "01d" # Default to clear day icon

        if icon_descriptor in ["sunny", "clear"]:   # Clear sky
            icon = "01d"
        elif icon_descriptor in ["mostly_sunny"]: # Mainly clear
            icon = "022d"
        elif icon_descriptor in ["partly_cloudy"]: # Partly cloudy
            icon = "02d"
        elif icon_descriptor in ["cloudy"]: # Overcast
            icon = "04d"
        elif icon_descriptor in ["light_shower"]: # Drizzle, showers, rain: Light
            icon = "51d"
        elif icon_descriptor in ["shower"]: # Drizzle, showers, rain: Moderatr
            icon = "53d"
        elif icon_descriptor in ["heavy_shower", "light_rain", "rain"]: # Drizzle, showers, rain: Heavy
            icon = "09d"
        elif icon_descriptor in ["fog"]: # Fog
            icon = "50d"
        elif icon_descriptor in ["snow", "frost"]:     # Snow grain
            icon = "77d"
        elif icon_descriptor in ["storm", "cyclone"]: # Thunderstorm
            icon = "11d"
        elif icon_descriptor in ["windy", "dusty"]: #
            icon = "wind"
        elif icon_descriptor in ["hazy"]: #
            icon = "visibility"

        if is_day == 0:
            if icon == "01d":
                icon = "01n"      # Clear sky night
            elif icon == "022d":
                icon = "022n"     # Mainly clear night
            elif icon == "02d":
                icon = "02n"      # Partly cloudy night
            elif icon == "10d":
                icon = "10n"      # Rain night

        return icon

    def get_bom_au_wind_arrow(self, direction: str) -> str:
        DIRECTIONS_MAP = {
            "N": "↓",
            "NNE": "↙",
            "NE": "↙",
            "ENE": "←",
            "E": "←",
            "ESE": "←",
            "SE": "↖",
            "SSE": "↖",
            "S": "↑",
            "SSW": "↗",
            "SW": "↗",
            "WSW": "→",
            "W": "→",
            "WNW": "↘",
            "NW": "↘",
            "NNW": "↘"
        }
        if DIRECTIONS_MAP[direction] is not None:
            return DIRECTIONS_MAP[direction]

        return "↑"

def calculate_relative_humidity(T_air_c, Td_c):
    """
    Calculates relative humidity (%) from air temperature and dew point temperature (°C).
    Uses the Magnus formula approximation.
    """
    # Calculate saturation vapor pressure at dew point (actual vapor pressure)
    e_s_td = 6.112 * math.exp((17.67 * Td_c) / (Td_c + 243.5))

    # Calculate saturation vapor pressure at air temperature
    e_s_t_air = 6.112 * math.exp((17.67 * T_air_c) / (T_air_c + 243.5))

    # Calculate relative humidity as a percentage
    rh = (e_s_td / e_s_t_air) * 100

    # Ensure RH is within a valid range
    if rh > 100:
        rh = 100.0
    elif rh < 0:
        rh = 0.0

    return round(rh, 2)
