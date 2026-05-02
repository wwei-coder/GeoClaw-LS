import warnings

def suppress_known_third_party_warnings() -> None:
    """Hide noisy import-time warnings from pinned third-party dependencies."""
    warnings.filterwarnings(
        "ignore",
        message=r"pkg_resources is deprecated as an API\..*",
        category=UserWarning,
        module=r"jieba\._compat",
    )
    try:
        from authlib.deprecate import AuthlibDeprecationWarning
    except ImportError:
        authlib_warning = Warning
    else:
        authlib_warning = AuthlibDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r"authlib\.jose module is deprecated, please use joserfc instead\..*",
        category=authlib_warning,
    )
