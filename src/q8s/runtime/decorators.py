import base64
import sys
import traceback
from dataclasses import is_dataclass
from functools import wraps
from typing import Type, TypeVar

from omegaconf import OmegaConf

T = TypeVar("T")


def with_app_config(config_cls: Type[T]):
    """
    Decorator that:
    - reads base64-encoded config from sys.argv[1]
    - merges it with a structured OmegaConf dataclass
    - resolves the config
    - passes the config instance into the function
    """

    if not is_dataclass(config_cls):
        raise TypeError("config_cls must be a dataclass")

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cfg = None
            trace: str = None

            if len(sys.argv) < 2:
                raise RuntimeError(
                    "Missing base64-encoded config argument (expected sys.argv[1])"
                )

            try:
                raw_input = base64.b64decode(sys.argv[1]).decode("utf-8")

                cfg = OmegaConf.merge(
                    OmegaConf.structured(config_cls),
                    OmegaConf.create(raw_input),
                )
                OmegaConf.resolve(cfg)
            except Exception:
                trace = traceback.format_exc()

            return func(cfg, trace, *args, **kwargs)

        return wrapper

    return decorator
