import logging

try:
    import psutil
except ImportError:
    psutil = None

# Default logger
fallbackLogger = logging.getLogger('large_image')
fallbackLogger.setLevel(logging.INFO)
fallbackLogHandler = logging.NullHandler()
fallbackLogHandler.setLevel(logging.NOTSET)
fallbackLogger.addHandler(fallbackLogHandler)

ConfigValues = {
    'logger': fallbackLogger,
    'logprint': fallbackLogger,

    # For tiles
    'cache_backend': None,  # 'python' or 'memcached'
    # 'python' cache can use 1/(val) of the available memory
    'cache_python_memory_portion': 32,
    # cache_memcached_url may be a list
    'cache_memcached_url': '127.0.0.1',
    'cache_memcached_username': None,
    'cache_memcached_password': None,

    # Generally, these keys are the form of "cache_<cacheName>_<key>"

    # For tilesources.  These are also limited by available file handles.
    # 'python' cache can use 1/(val) of the available memory based on a very
    # rough estimate of the amount of memory used by a tilesource
    'cache_tilesource_memory_portion': 8,
    # If >0, this is the maximum number of tilesources that will be cached
    'cache_tilesource_maximum': 0,

    'max_small_image_size': 4096,

    # Should ICC color correction be applied by default
    'icc_correction': True,

    # The maximum size of an annotation file that will be ingested into girder
    # via direct load
    'max_annotation_input_file_length': 1 * 1024 ** 3 if not psutil else max(
        1 * 1024 ** 3, psutil.virtual_memory().total // 16),
}


def getConfig(key=None, default=None):
    """
    Get the config dictionary or a value from the cache config settings.

    :param key: if None, return the config dictionary.  Otherwise, return the
        value of the key if it is set or the default value if it is not.
    :param default: a value to return if a key is requested and not set.
    :returns: either the config dictionary or the value of a key.
    """
    if key is None:
        return ConfigValues
    return ConfigValues.get(key, default)


def setConfig(key, value):
    """
    Set a value in the config settings.

    :param key: the key to set.
    :param value: the value to store in the key.
    """
    curConfig = getConfig()
    if curConfig.get(key) is not value:
        curConfig[key] = value
