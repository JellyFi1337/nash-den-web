"""Обращения к базе из потока бота. Соединение не остаётся открытым между тиками."""

from django.db import close_old_connections


def db(func, /, *args, **kwargs):
    close_old_connections()
    try:
        return func(*args, **kwargs)
    finally:
        close_old_connections()
