""" Retrieve menu from KAIST homepage """
import argparse
import datetime
from enum import Enum, unique
from html.parser import HTMLParser
from itertools import zip_longest
from pathlib import Path
import sys
import time
from unicodedata import east_asian_width

import requests

CODE = {
    "east": "east1",
    "east2": "east2",
    "hwaam": "hawam",
    "munji": "icc",
    "north": "fclt",
    "n6": "emp",
    "west": "west",
}

MENU_URL = "https://www.kaist.ac.kr/kr/html/campus/053001.html?dvs_cd={code}&stt_dt={date}"  # pylint:disable=line-too-long


@unique
class MenuParserState(Enum):
    """State Enum for MenuParser"""

    OUT_OF_TABLE = 0
    IN_TABLE = 1
    IN_TBODY = 2
    IN_TR = 3
    BREAKFAST = 4
    LUNCH = 5
    DINNER = 6
    TERMINATE = 7

    def succ(self) -> "MenuParserState":
        """Return the successor state."""
        assert self.value is not self.TERMINATE
        return MenuParserState(self.value + 1)


class MenuParser(HTMLParser):
    """Class that Parses Menu"""

    TAG_OF_INTEREST = {
        MenuParserState.IN_TABLE: "tbody",
        MenuParserState.IN_TBODY: "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self._state: MenuParserState = MenuParserState.OUT_OF_TABLE
        self._data: dict[MenuParserState, list[str]] = {}
        self._long_name = False

    def handle_starttag(self, tag, attrs) -> None:
        if self._state is MenuParserState.OUT_OF_TABLE:
            if tag == "table":
                for name, value in attrs:
                    if name == "class" and value == "table":
                        self._state = MenuParserState.IN_TABLE
        elif self._state is MenuParserState.TERMINATE:
            return
        else:
            if tag == self.TAG_OF_INTEREST.get(
                self._state, "td"
            ):  # default value td
                self._state = self._state.succ()

    def handle_endtag(self, tag) -> None:
        if self._state is MenuParserState.DINNER:
            if tag == "td":
                self._state = MenuParserState.TERMINATE

    def handle_data(self, data) -> None:
        if (
            self._state is MenuParserState.BREAKFAST
            or self._state is MenuParserState.LUNCH
            or self._state is MenuParserState.DINNER
        ):
            if self._state not in self._data:
                self._data[self._state] = []
            data = " ".join(data.split())
            if data:
                if self._long_name:
                    # encountered " in name
                    if data[-1] == '"':
                        data = data[:-1]  # remove "
                        self._long_name = False
                    self._data[self._state][-1] += " " + data
                else:
                    if data[0] == '"' and data.count('"') == 1:
                        data = data[1:]
                        self._long_name = True
                    self._data[self._state].append(data)

    @property
    def data(self) -> tuple[list[str], list[str], list[str]]:
        """Return a tuple of breakfast, lunch, and dinner menus"""
        return (
            self._data[MenuParserState.BREAKFAST],
            self._data[MenuParserState.LUNCH],
            self._data[MenuParserState.DINNER],
        )


def build_argparser() -> argparse.ArgumentParser:
    """Create an ArgumentParser for the application"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--refresh", action="store_true", default=False)
    parser.add_argument("target", default="n6", nargs="?", choices=CODE.keys())
    return parser


def compare_date(doi, doi_string):
    """Compare doi(date object) and doi_string(string)"""
    doi_ = datetime.datetime.strptime(doi_string, "%Y-%m-%d").date()
    return doi_ == doi


def date_of_interest():
    """Return tommorow if it's past 8 pm, otherwise today"""
    now = datetime.datetime.today()
    if now.hour > 19:
        now += datetime.timedelta(days=1)
    return now.date()


def max_len(strings) -> int:
    """Return the length of the maximum length string in `strings`"""
    return max(total_width(x) for x in strings)


def pad_string(string, padding, char=" ") -> str:
    """Pad a unicode string"""
    width = total_width(string)
    assert width <= padding
    return string + char * (padding - width)


def print_menu(doi, breakfast, lunch, dinner, file=sys.stdout) -> None:
    """Print the menu in a tabular form"""
    print(f"Date: {doi:%Y}-{doi:%m}-{doi:%d}", file=file)
    breakfast_width = max_len(["breakfast"] + breakfast)
    lunch_width = max_len(["lunch"] + lunch)
    dinner_width = max_len(["dinner"] + dinner)

    def format_line(breakfast_, lunch_, dinner_):
        """Format a line in a table"""
        return (
            f"| {pad_string(breakfast_, breakfast_width)} "
            f"| {pad_string(lunch_, lunch_width)} "
            f"| {pad_string(dinner_, dinner_width)} |"
        )

    seperator_str = (
        f"+-{pad_string('', breakfast_width, '-')}-"
        f"+-{pad_string('', lunch_width, '-')}-"
        f"+-{pad_string('', dinner_width, '-')}-+"
    )
    print(seperator_str, file=file)
    print(format_line("BREAKFAST", "LUNCH", "DINNER"), file=file)
    print(seperator_str, file=file)
    for dishes in zip_longest(breakfast, lunch, dinner, fillvalue=""):
        print(format_line(*dishes), file=file)
    print(seperator_str, file=file)


def total_width(string) -> int:
    """Calculate total width of the string"""
    width = 0
    for char in string:
        result = east_asian_width(char)
        if result in "WF":
            width += 2
        else:
            width += 1
    return width


def update_data(code, date) -> tuple[list[str], list[str], list[str]]:
    """Fetch menu data of `date` from server."""
    while True:
        response = requests.get(
            MENU_URL.format(code=code, date=date.strftime("%Y-%m-%d")),
            timeout=10,
        )
        response.raise_for_status()
        parser = MenuParser()
        response.encoding = "utf8"
        parser.feed(response.text)
        try:
            data = parser.data
        except KeyError:
            time.sleep(0.5)
            continue
        return data


def main(args):
    """main function for menu module"""
    cache_dir = Path().home() / ".cache" / "kaistmenu"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / args.target
    doi = date_of_interest()
    if args.refresh:
        data = update_data(code=CODE[args.target], date=doi)
        print_menu(doi, *data)
        with open(cache_path, "w", encoding="utf-8") as cache:
            print_menu(doi, *data, cache)
    else:
        with open(cache_path, "a+", encoding="utf-8") as cache:
            first = True
            cache.seek(0)
            for line in cache:
                if first:
                    parsed = line.split()
                    if len(parsed) != 2 or not compare_date(doi, parsed[1]):
                        break
                    first = False
                print(line.strip())
            else:
                if not first:
                    return
            cache.truncate(0)
            data = update_data(code=CODE[args.target], date=doi)
            print_menu(doi, *data)
            print_menu(doi, *data, file=cache)


def main_cli():
    main(build_argparser().parse_args())


if __name__ == "__main__":
    main_cli()
