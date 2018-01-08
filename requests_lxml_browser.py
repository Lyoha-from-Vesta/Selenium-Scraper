import logging
from lxml import html, etree
import requests
from lxml.html import HtmlElement

from abc_browser import ABCBrowser


class RequestsLxmlBrowser(ABCBrowser):
    _session = None
    _parsed_page = None

    def __init__(self, **kvargs):
        """
        :param kvargs: no_session
        """
        if kvargs.get('no_session', False):
            self._session = requests.Session()

        super().__init__(**kvargs)

    def __del__(self):
        if self._session is not None:
            self._session.close()

    def get(self, url):
        if self._session is None:
            resp = requests.get(url)
        else:
            resp = self._session.get(url)

        if resp.status_code != 200:
            logging.warning(f'Error {resp.status_code} opening URL "{url}": {resp.text}')
            return resp.status_code

        self._parsed_page = html.fromstring(resp.content)
        return 200

    def find_elements_by_xpath(self, xpath, web_element=None):
        try:
            if isinstance(web_element, HtmlElement):
                return web_element.xpath(xpath)
            else:
                return self._parsed_page.xpath(xpath)
        except Exception as ex:
            logging.warning(f'{ex}, {xpath}')
            return []

    def get_element_attribute(self, element, attribute):
        if attribute.lower() == 'innerhtml':
            return etree.tostring(element, pretty_print=True)
            # return ''.join([etree.tostring(child).decode('utf-8') for child in element.iterdescendants()])
        else:
            return element.attrib.get(attribute)

    def get_current_page_as_element(self):
        return self._parsed_page

    def scroll_to_element(self, element):
        pass
