"""Bounded configuration for every node of the LABSEAT application."""
import os


def integer(name, default, minimum=1, maximum=10000):
    try:
        value = int(os.getenv(name) or str(default))
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value


def database_pool():
    # Pool per ECS process; rolling tasks, background pools and reserve are budgeted in Terraform.
    size = integer('DB_POOL_SIZE', 3, maximum=3)
    integer('DB_MAX_OVERFLOW', 0, minimum=0, maximum=0)
    return size
