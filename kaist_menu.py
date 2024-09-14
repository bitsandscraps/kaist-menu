""" Retrieve menu from KAIST homepage """

import argparse
import datetime
from enum import Enum, unique
from html.parser import HTMLParser
from itertools import zip_longest
from pathlib import Path
from typing import NamedTuple
from unicodedata import east_asian_width

import dateutil.parser
import requests
from requests.adapters import HTTPAdapter, Retry
import tomlkit

CODE = {
    "east": "east1",
    "east2": "east2",
    "hwaam": "hawam",
    "munji": "icc",
    "north": "fclt",
    "n6": "emp",
    "west": "west",
}
CONFIG_PATH = Path().home() / ".config" / "kaistmenu" / "kaistmenurc"
MENU_URL = "https://www.kaist.ac.kr/kr/html/campus/053001.html?dvs_cd={code}&stt_dt={date}"  # pylint:disable=line-too-long


class MenuData(NamedTuple):
    breakfast: list[str]
    lunch: list[str]
    dinner: list[str]


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
    def data(self) -> MenuData:
        """Return a tuple of breakfast, lunch, and dinner menus"""
        return MenuData(
            breakfast=strip_strings(self._data[MenuParserState.BREAKFAST]),
            lunch=strip_strings(self._data[MenuParserState.LUNCH]),
            dinner=strip_strings(self._data[MenuParserState.DINNER]),
        )


def build_argparser() -> argparse.ArgumentParser:
    """Create an ArgumentParser for the application"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            config = tomlkit.load(config_file).value
    except FileNotFoundError:
        config = {}
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", default="")
    parser.add_argument("-r", "--refresh", action="store_true", default=False)
    parser.add_argument(
        "-l", "--max-length", type=int, default=config.get("max_length", 100)
    )
    parser.add_argument(
        "--max-retries", type=int, default=config.get("max_retries", 10)
    )
    parser.add_argument("--save-rc", action="store_true")
    parser.add_argument(
        "target",
        default=config.get("target", "n6"),
        nargs="?",
        choices=CODE.keys(),
    )
    return parser


def compare_date(doi, doi_string):
    """Compare doi(date object) and doi_string(string)"""
    doi_ = datetime.datetime.strptime(doi_string, "%Y-%m-%d").date()
    return doi_ == doi


def date_of_interest(date: str) -> datetime.date:
    """Return the date of interest.

    If date is not given, return tomorrow if it's past 8 pm, otherwise today.
    If date is given as a number, add it to today's date,
    e.g., +1 means tomorrow and +2 means the day after tomorrow.
    Otherwise, parse the string as a date.
    """
    if not date:
        now = datetime.datetime.today()
        if now.hour > 19:
            now += datetime.timedelta(days=1)
        return now.date()
    if date.startswith("+"):
        now = datetime.datetime.today()
        now += datetime.timedelta(days=int(date))
        return now.date()
    return dateutil.parser.parse(date)


def max_len(strings) -> int:
    """Return the length of the maximum length string in `strings`"""
    return max(total_width(x) for x in strings)


def pad_string(string, padding, char=" ") -> str:
    """Pad a unicode string"""
    width = total_width(string)
    assert width <= padding
    return string + char * (padding - width)


def print_menu(data: MenuData, doi: datetime.date, *, max_length: int) -> None:
    """Print the menu in a tabular form"""
    print(f"Date: {doi:%Y}-{doi:%m}-{doi:%d}")

    breakfast_width = max_len(["BREAKFAST"] + data.breakfast)
    lunch_width = max_len(["LUNCH"] + data.lunch)
    dinner_width = max_len(["DINNER"] + data.dinner)

    if breakfast_width + lunch_width + dinner_width > max_length:
        length_list = sorted([breakfast_width, lunch_width, dinner_width])
        if length_list[0] * 3 > max_length:
            max_length = max_length // 3
        elif length_list[0] + 2 * length_list[1] > max_length:
            max_length = (max_length - length_list[0]) // 2
        else:
            max_length = max_length - length_list[0] - length_list[1]

    breakfast = split_strings(data.breakfast, max_length)
    lunch = split_strings(data.lunch, max_length)
    dinner = split_strings(data.dinner, max_length)
    breakfast_width = min(breakfast_width, max_length)
    lunch_width = min(lunch_width, max_length)
    dinner_width = min(dinner_width, max_length)

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
    print(seperator_str)
    print(format_line("BREAKFAST", "LUNCH", "DINNER"))
    print(seperator_str)
    for dishes in zip_longest(breakfast, lunch, dinner, fillvalue=""):
        print(format_line(*dishes))
    print(seperator_str)


def read_cache(cache_path: Path, doi: datetime.date) -> MenuData:
    with open(cache_path, "r", encoding="utf-8") as cache:
        results = dict(tomlkit.load(cache))
    if doi != results["date"]:
        raise ValueError("Cache is outdated.")
    return MenuData(
        breakfast=results["breakfast"].value,  # type: ignore
        lunch=results["lunch"].value,  # type: ignore
        dinner=results["dinner"].value,  # type: ignore
    )


def split_strings(data: list[str], max_length: int) -> list[str]:
    new_data = []
    for string in data:
        new_string = ""
        length = 0
        for char in string:
            char_length = 2 if east_asian_width(char) in "WF" else 1
            new_length = length + char_length
            if new_length > max_length:
                new_data.append(new_string)
                new_string = char
                length = char_length
            else:
                length = new_length
                new_string += char
        if new_string:
            new_data.append(new_string)
    return new_data


def strip_strings(data: list[str]) -> list[str]:
    return [string.strip() for string in data]


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


def update_data(
    code: str, date: datetime.date, max_retries: int = 10
) -> MenuData:
    """Fetch menu data of `date` from server."""
    session = requests.Session()
    retries = Retry(backoff_factor=0.1, total=max_retries)
    session.mount("https://", HTTPAdapter(max_retries=retries))
    response = session.get(
        MENU_URL.format(code=code, date=date.strftime("%Y-%m-%d")),
        timeout=10,
    )
    response.raise_for_status()
    parser = MenuParser()
    response.encoding = "utf8"
    parser.feed(response.text)
    return parser.data


def update_and_print(
    cache_path: Path,
    code: str,
    doi: datetime.date,
    max_length: int,
    max_retries: int,
    rewrite_cache: bool = True,
):
    data = update_data(code=code, date=doi, max_retries=max_retries)
    print_menu(data, doi, max_length=max_length)
    if rewrite_cache:
        write_cache(cache_path, data, doi)


def write_cache(cache_path: Path, data: MenuData, doi: datetime.date):
    with open(cache_path, "w", encoding="utf-8") as cache:
        tomlkit.dump(
            {
                "date": doi,
                "breakfast": data.breakfast,
                "lunch": data.lunch,
                "dinner": data.dinner,
            },
            cache,
        )


def main(args):
    """main function for menu module"""
    cache_dir = Path().home() / ".cache" / "kaistmenu"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / f"{args.target}.toml"
    doi = date_of_interest(args.date)
    if args.refresh or args.date:
        update_and_print(
            cache_path=cache_path,
            code=CODE[args.target],
            doi=doi,
            max_length=args.max_length,
            max_retries=args.max_retries,
            rewrite_cache=args.date == "",
        )
    else:
        try:
            data = read_cache(cache_path, doi)
        except (FileNotFoundError, KeyError, ValueError):
            print("Refreshing cache")
            update_and_print(
                cache_path=cache_path,
                code=CODE[args.target],
                doi=doi,
                max_length=args.max_length,
                max_retries=args.max_retries,
            )
        else:
            print_menu(data, doi, max_length=args.max_length)
    if args.save_rc:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as config_file:
            tomlkit.dump(
                {
                    "max_length": args.max_length,
                    "max_retries": args.max_retries,
                    "target": args.target,
                },
                config_file,
            )


def main_cli():
    main(build_argparser().parse_args())


if __name__ == "__main__":
    main_cli()
