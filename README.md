# KAIST Menu

A command line tool that prints today's menu of KAIST cafeterias.

![Example Usage](example.png)

In the previous screenshot, I've aliased `m` with `python menu.py`.

# Prerequisites

Uses python3 and python library [requests](http://docs.python-requests.org/en/master/).

``` shellsession
$ pip3 install requests
```

# Usage

``` shellsession
python menu.py
```

If the cache is corrupted for some reason, you can refresh it by

``` shellsession
python menu.py -r
```
or
``` shellsession
python menu.py --refresh
```

If a code is given as a positional argument, it prints the menu of the
corresponding cafeteria. Default is N6.
``` shellsession
python menu.py north
```
## List of Available Codes

* 카이마루(북측 카페테리아): north
* 서맛골(서측 식당): west
* 동맛골(동측 학생식당): east
* 동맛골(동측 교직원식당): east2
* 교수회관: n6
