import abc


class ABCBrowser(abc.ABC):
    _current_url = None

    def __init__(self, **kvargs):
        pass

    def __del__(self):
        pass

    def get_current_url(self):
        return self._current_url

    @abc.abstractmethod
    def get(self, url):
        self._current_url = url

    @abc.abstractmethod
    def find_elements_by_xpath(self, xpath, web_element):
        pass

    @abc.abstractmethod
    def get_element_attribute(self, element, attribute):
        pass

    @abc.abstractmethod
    def get_current_page_as_element(self):
        pass

    @abc.abstractmethod
    def scroll_to_element(self, element):
        pass