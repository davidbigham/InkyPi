from typing import Any


class BomWeatherAPIException(Exception):
    """
    BOM Weather API exception
    """


class ResultException(BomWeatherAPIException):
    """
    Exception occurred while processing result
    """

    def __init__(self, message: str, response: Any = None):
        self.message = message
        self.response = response


class ResultNotFound(BomWeatherAPIException):
    """
    No data found
    """
