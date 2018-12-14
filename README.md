# KAIST N6 Menu

A command line tool that prints today's menu of KAIST N6 cafeteria

![Example Usage](example.png)

In the previous screenshot, I've aliased `m` with [menu.sh](menu.sh).

# Prerequisites

Uses python3 and python library [requests](http://docs.python-requests.org/en/master/).

``` shellsession
$ pip3 install requests
```
or better, use [pipenv](https://docs.pipenv.org/)

``` shellsession
$ pipenv install
```

# Usage

``` shellsession
python -m menu
```

If the cache is corrupted for some reason, you can refresh it by

``` shellsession
python -m menu -r
```

[menu.sh](menu.sh) is a script for `pipenv` users. It will run the program regardless of the current working directory.
