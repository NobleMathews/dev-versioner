"""All custom exceptions raised by Dependency Inspector"""
import abc


class UnsupportedError(Exception):
    """Raised when an unsupported action is attempted"""

    @abc.abstractmethod
    def __init__(self):
        pass


class LanguageNotSupportedError(UnsupportedError):
    """Raised when language is currently not supported"""

    def __init__(self, lang):
        self.msg = f"{lang} is not currently supported"


class VCSNotSupportedError(UnsupportedError):
    """Raised when VCS used is not supported"""

    def __init__(self, package):
        self.msg = f"VCS used by {package} is not supported"
