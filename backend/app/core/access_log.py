import logging


class SkipPathsFilter(logging.Filter):
    """Drops uvicorn access-log records for the given request paths."""

    def __init__(self, paths):
        super().__init__()
        self.paths = set(paths)

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn logs: '%s - "%s %s HTTP/%s" %d' -> (client, method, full_path, version, status)
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            return args[2].split("?", 1)[0] not in self.paths
        return True


def skip_paths_in_access_log(paths) -> None:
    logging.getLogger("uvicorn.access").addFilter(SkipPathsFilter(paths))
