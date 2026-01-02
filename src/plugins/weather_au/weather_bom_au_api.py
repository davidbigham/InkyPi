from __future__ import annotations
from http import HTTPStatus
import json
import urllib.request
import urllib.parse
from collections.abc import Sequence, Mapping
from dataclasses import dataclass, field
from typing import Optional

from marshmallow import fields

from datetime import datetime

from dataclasses_json import dataclass_json, Undefined, config
from .exceptions import (
    ResultException,
    ResultNotFound
)

BOM_API_BASE_URL = "https://api.weather.bom.gov.au/v1"

# def datetime_decoder(datetime_str: str) -> datetime:
#     """Decodes an ISO 8601 formatted string into a datetime object."""
#     # datetime.fromisoformat() handles most ISO 8601 formats in Python 3.7+
#     return datetime.fromisoformat(datetime_str)
#
# def datetime_encoder(datetime_obj: datetime) -> str:
#     """Encodes a datetime object into an ISO 8601 formatted string."""
#     return datetime_obj.isoformat()

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Location:
    """
    Result of a location search. E.g.:
        {
			"geohash": "r1f93ck",
			"id": "Adelaide-r1f93ck",
			"name": "Adelaide",
			"postcode": "5000",
			"state": "SA"
		}
    """
    name: str
    geohash: str
    id: str
    postcode: Optional[str]
    state: str


    def details(self) -> LocationDetails:
        """
        Get details about a location.
        """

        data = Location._make_request(f"/locations/{self.geohash}")
        return LocationDetails(**data)

    def warnings(self) -> Sequence[LocationWarning]:
        """
        Get warnings for the location
        """
        data = Location._make_request(f"/locations/{self.geohash}/warnings")
        # return [LocationWarning(**item) for item in data] # this seems to ignore datetime and parses as string
        return [LocationWarning.from_dict(item) for item in data]

    def observations(self) -> LocationObservation:
        """
        Get observations for the location
        """
        data = Location._make_request(f"/locations/{self.geohash[:6]}/observations")
        # return LocationObservation(**data) # this seems to ignore datetime and parses as string
        return LocationObservation.from_dict(data)

    def forcast_daily(self) -> Sequence[LocationForecastDaily]:
        """
        Daily forecast for the location
        """

        data = Location._make_request(f"/locations/{self.geohash[:6]}/forecasts/daily")
        # return [LocationForecastDaily(**item) for item in data] # this seems to ignore datetime and parses as string
        return [LocationForecastDaily.from_dict(item) for item in data]

    def forcast_hourly(self) -> Sequence[LocationForecastHourly]:
        """
        Hourly forecast for the location
        """

        data = Location._make_request(f"/locations/{self.geohash[:6]}/forecasts/hourly")
        # return [LocationForecastHourly(**item) for item in data] # this seems to ignore datetime and parses as string
        return [LocationForecastHourly.from_dict(item) for item in data]

    @staticmethod
    def search(location_search: str) -> Sequence[Location]:
        data = Location._make_request(f"/locations", params={"search": location_search})
        # return [Location(**item) for item in data] # this seems to ignore datetime and parses as string
        return [Location.from_dict(item) for item in data]

    @staticmethod
    def search(latitude: float, longitude: float) -> Sequence[Location]:
        data = Location._make_request(f"/locations", params={"search": f"{latitude:.4f},{longitude:.4f}"})
        # return [Location(**item) for item in data] # this seems to ignore datetime and parses as string
        return [Location.from_dict(item) for item in data]

    @staticmethod
    def _make_request(url_path: str, *, params: Mapping[str, str] = None):
        url = f"{BOM_API_BASE_URL}{url_path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        print(url)

        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                return data.get("data")
        except urllib.error.HTTPError as e:
            if e.code == HTTPStatus.BAD_REQUEST:
                raise ResultNotFound("Requested item not found", e)
            else:
                raise ResultException("Request returned an error", e)


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class LocationDetails:
    """
    Details of a location. E.g.:
        {
		"geohash": "r1f90q5",
		"timezone": "Australia/Adelaide",
		"latitude": -34.94682312011719,
		"longitude": 138.5314178466797,
		"marine_area_id": "SA_MW011",
		"tidal_point": "SA_TP017",
		"has_wave": true,
		"id": "Adelaide Airport-r1f90q5",
		"name": "Adelaide Airport",
		"state": "SA"
	}
    """
    id: str
    name: str
    state: str
    geohash: str
    timezone: str
    latitude: float
    longitude: float
    marine_area_id: str
    tidal_point: str
    has_wave: bool

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class LocationWarning:
    """
    Details of a Warning. E.g.:
        {
			"id": "SA_MW011_IDS20201",
			"area_id": "SA_MW011",
			"type": "marine_wind_warning",
			"title": "Marine Wind Warning for South Australia",
			"short_title": "Marine Wind Warning",
			"state": "SA",
			"warning_group_type": "minor",
			"issue_time": "2025-12-29T23:04:15Z",
			"expiry_time": "2025-12-30T06:04:15Z",
			"phase": "renewal"
		}
    """
    id: str
    area_id: str
    type: str
    title: str
    short_title: str
    state: str
    warning_group_type: str
    phase: str
    issue_time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    expiry_time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class WindBase:
    speed_kilometre: float
    speed_knot: float


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Wind(WindBase):
    direction: str

# @dataclass_json(undefined=Undefined.EXCLUDE)
# @dataclass
# class Gust(WindBase):
Gust = WindBase

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MaxGust(WindBase):
    time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Temperature:
    value: float
    time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Station:
    bom_id: str
    name: str
    distance: float

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class LocationObservation:
    """
    Details of a location. E.g.:
    {
		"temp": 20.4,
		"temp_feels_like": 15.5,
		"wind": {
			"speed_kilometre": 30,
			"speed_knot": 16,
			"direction": "SE"
		},
		"gust": {
			"speed_kilometre": 43,
			"speed_knot": 23
		},
		"max_gust": {
			"speed_kilometre": 44,
			"speed_knot": 24,
			"time": "2025-12-30T00:38:00Z"
		},
		"max_temp": {
			"time": "2025-12-30T00:15:00Z",
			"value": 21.8
		},
		"min_temp": {
			"time": "2025-12-29T21:00:00Z",
			"value": 18.5
		},
		"rain_since_9am": 0,
		"humidity": 61,
		"station": {
			"bom_id": "023154",
			"name": "Adelaide Airport",
			"distance": 633
		}
	}
    """
    temp: float
    temp_feels_like: float
    humidity: int
    wind: Wind
    gust: Gust #WindBase #Gust
    max_gust: MaxGust
    max_temp: Temperature
    min_temp: Temperature
    rain_since_9am: float
    station: Station

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class RainDailyForecastAmount:
    min: float
    max: Optional[float]
    lower_range: float
    upper_range: float
    units: str

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class RainDailyForecast:
    amount: RainDailyForecastAmount
    chance: int
    chance_of_no_rain_category: str
    precipitation_amount_25_percent_chance: float
    precipitation_amount_50_percent_chance: float
    precipitation_amount_75_percent_chance: float



@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class UV:
    category: Optional[str]
    max_index: Optional[int]
    start_time: Optional[datetime] = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    end_time: Optional[datetime] = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Astronomical:
    sunrise_time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    sunset_time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class FireDangerCategory:
    text: Optional[str]
    default_colour: Optional[str]
    dark_mode_colour: Optional[str]

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class Now:
    is_night: bool
    now_label: str
    later_label: str
    temp_now: float
    temp_later: float

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class LocationForecastDaily:
    """
    Details of a Daily Forecast. E.g.:
    	{
			"rain": {
				"amount": {
					"min": 0,
					"max": null,
					"lower_range": 0,
					"upper_range": 0,
					"units": "mm"
				},
				"chance": 5,
				"chance_of_no_rain_category": "very high",
				"precipitation_amount_25_percent_chance": 0,
				"precipitation_amount_50_percent_chance": 0,
				"precipitation_amount_75_percent_chance": 0
			},
			"uv": {
				"category": "extreme",
				"end_time": "2025-12-30T07:00:00Z",
				"max_index": 12,
				"start_time": "2025-12-29T22:30:00Z"
			},
			"astronomical": {
				"sunrise_time": "2025-12-29T19:35:03Z",
				"sunset_time": "2025-12-30T10:03:40Z"
			},
			"date": "2025-12-29T13:30:00Z",
			"temp_max": 25,
			"temp_min": 17,
			"extended_text": "Cloudy. Winds south to southeasterly 25 to 35 km/h.",
			"icon_descriptor": "cloudy",
			"short_text": "Becoming windy. Cloudy.",
			"surf_danger": null,
			"fire_danger": "No Rating",
			"fire_danger_category": {
				"text": "No Rating",
				"default_colour": null,
				"dark_mode_colour": null
			},
			"now": {                            // OPTIONAL (only on current day)
				"is_night": false,
				"now_label": "Max",
				"later_label": "Overnight min",
				"temp_now": 25,
				"temp_later": 13
			}
		},,
    """
    rain: RainDailyForecast
    uv: UV
    astronomical: Astronomical
    temp_max: float
    temp_min: Optional[float]
    extended_text: str
    icon_descriptor: str
    short_text: str
    surf_danger: Optional[str]
    fire_danger: Optional[str]
    fire_danger_category: FireDangerCategory
    date: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    now: Optional[Now] = None # only on current day


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class RainHourlyForecastAmount:
    min: float
    max: Optional[float]
    units: str

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class RainHourlyForecast:
    amount: RainHourlyForecastAmount
    chance: int
    precipitation_amount_10_percent_chance: float
    precipitation_amount_25_percent_chance: float
    precipitation_amount_50_percent_chance: float



@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class WindForecastHourly(Wind):
    gust_speed_knot: float
    gust_speed_kilometre: float

@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class LocationForecastHourly:
    """
    Details of an Hourly Forecast. E.g.:
    	{
			"rain": {
				"amount": {
					"min": 0,
					"max": null,
					"units": "mm"
				},
				"chance": 0,
				"precipitation_amount_10_percent_chance": 0,
				"precipitation_amount_25_percent_chance": 0,
				"precipitation_amount_50_percent_chance": 0
			},
			"temp": 24,
			"temp_feels_like": 21,
			"dew_point": 13,
			"wind": {
				"speed_knot": 18,
				"speed_kilometre": 33,
				"direction": "SSE",
				"gust_speed_knot": 24,
				"gust_speed_kilometre": 44
			},
			"relative_humidity": 51,
			"uv": 7,
			"icon_descriptor": "cloudy",
			"next_three_hourly_forecast_period": "2025-12-30T03:00:00Z",
			"time": "2025-12-30T01:00:00Z",
			"is_night": false,
			"next_forecast_period": "2025-12-30T02:00:00Z"
		},
    """
    rain: RainHourlyForecast
    temp: float
    temp_feels_like: float
    dew_point: float
    wind: WindForecastHourly
    relative_humidity: int
    uv: int
    icon_descriptor: str
    is_night: bool
    time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    next_forecast_period: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    next_three_hourly_forecast_period: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
