# DLP01 - 論壇自動下載程式

from .version import (
    VERSION,
    VERSION_DATE,
    APP_NAME,
    APP_DISPLAY_NAME,
    get_version,
    get_version_tuple,
    get_version_info,
    get_window_title,
    get_about_text,
    compare_versions,
    is_newer_version,
)

__version__ = VERSION
__all__ = [
    'VERSION',
    'VERSION_DATE',
    'APP_NAME',
    'APP_DISPLAY_NAME',
    'get_version',
    'get_version_tuple',
    'get_version_info',
    'get_window_title',
    'get_about_text',
    'compare_versions',
    'is_newer_version',
]
